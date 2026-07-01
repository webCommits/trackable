from django.db import models


AVERAGE_WEEKS_PER_MONTH = 4.348


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

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.position}"

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

    def get_target_hours(self, year, month):
        """Target hours (Soll) for this profile in a given month.

        Formula: weekly_hours × 4.348 (average weeks per month).
        Pro-rata bei Vertragsbeginn/-ende im Monat.
        Feiertage kürzen die Soll-Stunden nicht.
        Falls back to weekly_hours if weekly_target_hours is not set.
        """
        import calendar
        from datetime import date

        base = float(self.weekly_target_hours) if self.weekly_target_hours is not None else float(self.weekly_hours)
        full_target = base * AVERAGE_WEEKS_PER_MONTH

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
