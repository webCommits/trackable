from django.db import models


class Profile(models.Model):
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="profiles"
    )
    title = models.CharField(max_length=200)
    position = models.CharField(max_length=200)
    address = models.CharField(max_length=500, blank=True, null=True)
    weekly_hours = models.DecimalField(max_digits=4, decimal_places=2)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
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

        last_day = calendar.monthrange(year, month)[1]
        start_date = datetime(year, month, 1)
        end_date = datetime(year, month, last_day, 23, 59, 59)

        return self.time_entries.filter(
            date__range=[start_date.date(), end_date.date()]
        )

    def get_monthly_hours(self, year, month):
        entries = self.get_monthly_entries(year, month)
        return sum(entry.hours_worked for entry in entries)

    def get_monthly_earnings(self, year, month):
        hours = self.get_monthly_hours(year, month)
        return hours * self.hourly_rate
