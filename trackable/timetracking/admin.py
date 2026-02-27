from django.contrib import admin
from trackable.timetracking.models import TimeEntry


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = [
        "date",
        "start_time",
        "end_time",
        "hours_worked",
        "pause_duration",
        "profile",
    ]
    list_filter = ["date", "profile"]
    search_fields = ["profile__title", "profile__position"]
    date_hierarchy = "date"
