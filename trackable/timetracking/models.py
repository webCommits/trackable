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
