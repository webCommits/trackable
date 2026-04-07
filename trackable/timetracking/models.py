from django.db import models
from django.utils import timezone


class TimeEntry(models.Model):
    profile = models.ForeignKey(
        "profiles.Profile", on_delete=models.CASCADE, related_name="time_entries"
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    pause_duration = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    hours_worked = models.DecimalField(max_digits=4, decimal_places=2, editable=False)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-start_time"]

    def __str__(self):
        return f"{self.date} - {self.start_time} to {self.end_time}"

    def calculate_hours(self):
        from datetime import datetime, timedelta

        start = datetime.combine(self.date, self.start_time)
        end = datetime.combine(self.date, self.end_time)

        if end < start:
            end += timedelta(days=1)

        total_hours = (end - start).total_seconds() / 3600
        self.hours_worked = max(0, total_hours - float(self.pause_duration))

        return self.hours_worked

    def save(self, *args, **kwargs):
        self.hours_worked = self.calculate_hours()
        super().save(*args, **kwargs)


class ActiveTimer(models.Model):
    """Tracks a running timer for a profile. One per profile per user."""

    profile = models.ForeignKey(
        "profiles.Profile", on_delete=models.CASCADE, related_name="active_timers"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="active_timers"
    )
    start_time = models.DateTimeField()
    pause_time = models.DateTimeField(null=True, blank=True)
    total_paused_seconds = models.IntegerField(default=0)
    is_paused = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["profile", "user"]
        ordering = ["-created_at"]

    def __str__(self):
        status = "paused" if self.is_paused else "running"
        return f"{self.profile.title} - {status} since {self.start_time}"


class VacationEntry(models.Model):
    profile = models.ForeignKey(
        "profiles.Profile", on_delete=models.CASCADE, related_name="vacation_entries"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    notes = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.start_date} – {self.end_date} ({self.profile.title})"

    @property
    def workdays(self):
        """Mon–Fri days in the vacation period, minus public holidays."""
        from datetime import timedelta
        from trackable.core.models import Holiday

        qs = Holiday.objects.filter(date__range=[self.start_date, self.end_date])
        org = getattr(self.profile.user, "organization_membership", None)
        if org:
            qs = qs.filter(organization=org.organization) | qs.filter(
                organization__isnull=True
            )
        holiday_dates = set(qs.values_list("date", flat=True))

        count = 0
        current = self.start_date
        while current <= self.end_date:
            if current.weekday() < 5 and current not in holiday_dates:
                count += 1
            current += timedelta(days=1)
        return count

    @property
    def weeks(self):
        return round(self.workdays / 5, 1)
