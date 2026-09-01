from django.db import models
from django.db.models import F, Q


AVERAGE_WEEKS_PER_MONTH = 4.348
TARGET_HOURS_WEEKLY = "weekly"
TARGET_HOURS_MONTHLY = "monthly"
TARGET_HOURS_PERIOD_CHOICES = [
    (TARGET_HOURS_WEEKLY, "Weekly"),
    (TARGET_HOURS_MONTHLY, "Monthly"),
]


class Profile(models.Model):
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="profiles"
    )
    title = models.CharField(max_length=200)
    position = models.CharField(max_length=200)
    address = models.CharField(max_length=500, blank=True, null=True)
    weekly_hours = models.DecimalField(max_digits=6, decimal_places=4)
    weekly_target_hours = models.DecimalField(
        max_digits=6, decimal_places=4, null=True, blank=True,
        verbose_name="Weekly target hours",
        help_text="Override target hours per week. If empty, uses weekly hours.",
    )
    target_hours_period = models.CharField(
        max_length=10,
        choices=TARGET_HOURS_PERIOD_CHOICES,
        default=TARGET_HOURS_WEEKLY,
        verbose_name="Target hours period",
    )
    monthly_target_hours = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Monthly target hours",
        help_text="Target hours per month. Used when target hours period is monthly.",
    )
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    contract_start_date = models.DateField(
        verbose_name="Contract start date",
        null=True, blank=True,
        help_text="Target hours are only calculated from this date onwards.",
    )
    contract_end_date = models.DateField(
        verbose_name="Contract end date",
        null=True, blank=True,
        help_text="Optional. Target hours stop after this date.",
    )
    internal_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.position}"

    @property
    def is_archived(self):
        return self.archived_at is not None

    def get_monthly_entries(self, year, month):
        from django.utils import timezone
        import calendar
        from datetime import datetime
        from trackable.timetracking.models import ENTRY_TYPE_ACTUAL

        last_day = calendar.monthrange(year, month)[1]
        start_date = datetime(year, month, 1)
        end_date = datetime(year, month, last_day, 23, 59, 59)

        return self.time_entries.filter(
            date__range=[start_date.date(), end_date.date()],
            entry_type=ENTRY_TYPE_ACTUAL,
        )

    def get_monthly_hours(self, year, month):
        entries = self.get_monthly_entries(year, month)
        return sum(entry.hours_worked for entry in entries)

    def get_monthly_earnings(self, year, month):
        hours = self.get_monthly_hours(year, month)
        return hours * self.hourly_rate

    def _get_working_days_in_month(self, year, month):
        """Count Mon–Fri days in a month excluding org-level holidays."""
        import calendar
        from datetime import date
        from trackable.core.models import Holiday

        org = getattr(self.user, "organization_membership", None)
        org_obj = org.organization if org else None

        _, last_day = calendar.monthrange(year, month)

        holidays = Holiday.objects.filter(date__year=year, date__month=month)
        if org_obj:
            holidays = holidays.filter(
                models.Q(organization=org_obj) | models.Q(organization__isnull=True)
            )
        holiday_dates = set(holidays.values_list("date", flat=True))

        count = 0
        for day in range(1, last_day + 1):
            d = date(year, month, day)
            if d.weekday() < 5 and d not in holiday_dates:
                # Respect contract start date
                if self.contract_start_date and d < self.contract_start_date:
                    continue
                # Respect contract end date
                if self.contract_end_date and d > self.contract_end_date:
                    continue
                count += 1
        return count

    def _count_weekdays_in_month(self, year, month):
        """Count Mon–Fri days in a month (no holiday exclusion, no contract filter)."""
        import calendar
        from datetime import date

        _, last_day = calendar.monthrange(year, month)
        count = 0
        for day in range(1, last_day + 1):
            d = date(year, month, day)
            if d.weekday() < 5:
                count += 1
        return count

    def _get_target_hours_config(self, year, month):
        """Config (profile or TargetHoursChange) effective for the given month."""
        import calendar
        from datetime import date

        last_day = calendar.monthrange(year, month)[1]
        month_end = date(year, month, last_day)

        change = (
            self.target_hours_changes.filter(
                Q(valid_from__isnull=True) | Q(valid_from__lte=month_end)
            )
            .order_by(F("valid_from").desc(nulls_last=True))
            .first()
        )
        return change or self

    def get_full_month_target_hours(self, year=None, month=None):
        """Full-month target hours before contract pro-rating.

        When year and month are given, uses the target-hours config that was
        effective for that month (see TargetHoursChange); otherwise uses the
        profile's current values.
        """
        config = self if year is None or month is None else self._get_target_hours_config(year, month)

        if (
            config.target_hours_period == TARGET_HOURS_MONTHLY
            and config.monthly_target_hours is not None
        ):
            return float(config.monthly_target_hours)

        weekly = (
            float(config.weekly_target_hours)
            if config.weekly_target_hours is not None
            else float(config.weekly_hours)
        )
        return weekly * AVERAGE_WEEKS_PER_MONTH

    def get_weekly_target_display_hours(self):
        """Weekly-equivalent target hours for display.

        History-aware: reflects the config effective for the current month,
        so a still-future change doesn't leak into "current" displays and a
        past change is picked up once its month arrives.
        """
        from django.utils import timezone

        today = timezone.localdate()
        config = self._get_target_hours_config(today.year, today.month)

        if (
            config.target_hours_period == TARGET_HOURS_MONTHLY
            and config.monthly_target_hours is not None
        ):
            return round(float(config.monthly_target_hours) / AVERAGE_WEEKS_PER_MONTH, 2)
        if config.weekly_target_hours is not None:
            return float(config.weekly_target_hours)
        return float(config.weekly_hours)

    def get_target_hours(self, year, month):
        """Target hours (Soll) for this profile in a given month.

        Formula: weekly target × 4.348 or configured monthly target.
        Pro-rata bei Vertragsbeginn/-ende im Monat.
        Feiertage kürzen die Soll-Stunden nicht.
        Falls back to weekly_hours if weekly_target_hours is not set.
        """
        import calendar
        from datetime import date

        full_target = self.get_full_month_target_hours(year, month)

        _, last_day = calendar.monthrange(year, month)
        month_start = date(year, month, 1)
        month_end = date(year, month, last_day)

        # Vertrag noch nicht begonnen oder bereits beendet
        if self.contract_start_date and self.contract_start_date > month_end:
            return 0.0
        if self.contract_end_date and self.contract_end_date < month_start:
            return 0.0

        # Vertrag umspannt den vollen Monat → kein Pro-rata nötig
        if (not self.contract_start_date or self.contract_start_date <= month_start) and (
            not self.contract_end_date or self.contract_end_date >= month_end
        ):
            return round(full_target, 2)

        # Teilmonat → Pro-rata anhand Werktage (Mo–Fr) im Vertragszeitraum
        total_weekdays = 0
        contract_weekdays = 0
        for day in range(1, last_day + 1):
            d = date(year, month, day)
            if d.weekday() >= 5:
                continue
            total_weekdays += 1
            if self.contract_start_date and d < self.contract_start_date:
                continue
            if self.contract_end_date and d > self.contract_end_date:
                continue
            contract_weekdays += 1

        if total_weekdays == 0:
            return 0.0
        return round(full_target * contract_weekdays / total_weekdays, 2)

    def get_balance(self, year, month):
        """Balance = actual hours − target hours.

        Positive = overtime (Überstunden), negative = deficit (Minusstunden).
        """
        actual = self.get_monthly_hours(year, month)
        target = self.get_target_hours(year, month)
        return round(float(actual) - float(target), 2)

    def _month_range(self, start_year, start_month, end_year, end_month):
        """Generate all (year, month) tuples from start to end inclusive, oldest first."""
        months = []
        y, m = start_year, start_month
        while (y, m) <= (end_year, end_month):
            months.append((y, m))
            if m == 12:
                y += 1
                m = 1
            else:
                m += 1
        return months

    def get_monthly_account_rows(self, until_year=None, until_month=None):
        """Return monthly account rows for display (newest first).

        Each row is a dict compatible with existing views:
        year, month, month_name, hours, target_hours, balance,
        cumulative_balance, earnings.

        Cumulative balance is computed chronologically (oldest → newest),
        then rows are returned newest first.
        """
        from datetime import datetime
        from django.utils import timezone
        from trackable.timetracking.models import ENTRY_TYPE_ACTUAL

        # Determine end month
        if until_year is not None and until_month is not None:
            end_year, end_month = until_year, until_month
        else:
            now = timezone.now().date()
            end_year, end_month = now.year, now.month

        # Earliest actual time entry month
        earliest = (
            self.time_entries.filter(entry_type=ENTRY_TYPE_ACTUAL)
            .order_by("date")
            .values_list("date", flat=True)
            .first()
        )

        # Determine start month
        if self.contract_start_date is not None:
            start_year, start_month = self.contract_start_date.year, self.contract_start_date.month
            if earliest is not None and (earliest.year, earliest.month) < (start_year, start_month):
                # Never hide months that already have actual time entries.
                start_year, start_month = earliest.year, earliest.month
        else:
            if earliest is not None:
                start_year, start_month = earliest.year, earliest.month
            else:
                start_year, start_month = end_year, end_month

        # Clamp end to contract_end_date if set
        if self.contract_end_date is not None:
            if self.contract_end_date.year < end_year or (
                self.contract_end_date.year == end_year and self.contract_end_date.month < end_month
            ):
                end_year, end_month = self.contract_end_date.year, self.contract_end_date.month

        # If start > end, return empty
        if (start_year, start_month) > (end_year, end_month):
            return []

        # All months oldest→newest
        all_months = self._month_range(start_year, start_month, end_year, end_month)

        # Compute rows chronologically
        rows = []
        cumulative = 0.0
        for y, m in all_months:
            hours = self.get_monthly_hours(y, m)
            target = self.get_target_hours(y, m)
            balance = self.get_balance(y, m)
            earnings = self.get_monthly_earnings(y, m)
            cumulative += balance
            month_label = datetime(y, m, 1).strftime("%B %Y")
            rows.append({
                "year": y,
                "month": m,
                "month_name": month_label,
                "hours": float(hours),
                "target_hours": target,
                "balance": balance,
                "cumulative_balance": round(cumulative, 2),
                "earnings": float(earnings),
            })

        # Return newest first
        return list(reversed(rows))

    def get_cumulative_balance(self, year, month):
        """Zeitkonto through the given month, including previous monthly balances."""
        rows = self.get_monthly_account_rows(until_year=year, until_month=month)
        selected = next(
            (row for row in rows if row["year"] == year and row["month"] == month),
            None,
        )
        if selected:
            return selected["cumulative_balance"]
        return rows[0]["cumulative_balance"] if rows else 0

    def apply_target_hours_change(
        self,
        *,
        period,
        weekly_hours,
        weekly_target_hours,
        monthly_target_hours,
        valid_from,
    ):
        """Set target hours, optionally effective from a given month onwards.

        If valid_from is None, the change applies retroactively to all
        months (pre-existing behavior): history is cleared and the values
        are written directly onto the profile.

        If valid_from is a date (normalized to the first of its month), the
        change only applies from that month onwards; earlier months keep
        whatever target hours were effective before.
        """
        from django.db import transaction

        with transaction.atomic():
            if valid_from is None:
                self.target_hours_changes.all().delete()
                self.target_hours_period = period
                self.weekly_hours = weekly_hours
                self.weekly_target_hours = weekly_target_hours
                self.monthly_target_hours = monthly_target_hours
                self.save()
                return

            valid_from = valid_from.replace(day=1)

            # No-op fast path: the config already effective for that month
            # already matches the requested values.
            current = self._get_target_hours_config(valid_from.year, valid_from.month)
            if (
                current.target_hours_period == period
                and current.weekly_hours == weekly_hours
                and current.weekly_target_hours == weekly_target_hours
                and current.monthly_target_hours == monthly_target_hours
            ):
                return

            if not self.target_hours_changes.exists():
                # Snapshot the current profile values as the baseline, so
                # months before valid_from keep the old target.
                TargetHoursChange.objects.create(
                    profile=self,
                    valid_from=None,
                    target_hours_period=self.target_hours_period,
                    weekly_hours=self.weekly_hours,
                    weekly_target_hours=self.weekly_target_hours,
                    monthly_target_hours=self.monthly_target_hours,
                )

            TargetHoursChange.objects.update_or_create(
                profile=self,
                valid_from=valid_from,
                defaults={
                    "target_hours_period": period,
                    "weekly_hours": weekly_hours,
                    "weekly_target_hours": weekly_target_hours,
                    "monthly_target_hours": monthly_target_hours,
                },
            )

            # Re-sync the profile's own fields from the config effective for
            # TODAY's month (not simply the newest record) — a future-dated
            # change must not leak into "current" displays before its month
            # arrives.
            from django.utils import timezone

            today = timezone.localdate()
            config = self._get_target_hours_config(today.year, today.month)
            if config is not self:
                self.target_hours_period = config.target_hours_period
                self.weekly_hours = config.weekly_hours
                self.weekly_target_hours = config.weekly_target_hours
                self.monthly_target_hours = config.monthly_target_hours
                self.save()


class TargetHoursChange(models.Model):
    """A target-hours configuration effective from a given month onwards.

    A record with valid_from=None is the baseline: the values that were
    effective "since the beginning" before any prospective change was made.
    Field names mirror Profile's target-hours fields so a change record and
    the profile itself can be used interchangeably as a target-hours config.
    """

    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="target_hours_changes"
    )
    valid_from = models.DateField(
        null=True,
        blank=True,
        help_text="First day of the month this change is effective from. "
        "Empty means baseline, valid since the beginning.",
    )
    target_hours_period = models.CharField(
        max_length=10,
        choices=TARGET_HOURS_PERIOD_CHOICES,
        default=TARGET_HOURS_WEEKLY,
    )
    weekly_hours = models.DecimalField(max_digits=6, decimal_places=4)
    weekly_target_hours = models.DecimalField(
        max_digits=6, decimal_places=4, null=True, blank=True
    )
    monthly_target_hours = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "valid_from"],
                name="uniq_target_hours_change_per_month",
                condition=Q(valid_from__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["profile"],
                name="uniq_target_hours_baseline",
                condition=Q(valid_from__isnull=True),
            ),
        ]

    def __str__(self):
        label = self.valid_from.strftime("%Y-%m") if self.valid_from else "baseline"
        return f"{self.profile} – {label}"
