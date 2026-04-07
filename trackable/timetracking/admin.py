from django.contrib import admin
from trackable.timetracking.models import TimeEntry, VacationEntry
from trackable.core.admin_site import custom_admin_site


@admin.register(TimeEntry, site=custom_admin_site)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = [
        "date",
        "start_time",
        "end_time",
        "hours_worked",
        "pause_duration",
        "notes",
        "profile",
    ]
    list_filter = ["date", "profile"]
    search_fields = ["profile__title", "profile__position", "notes"]
    date_hierarchy = "date"


@admin.register(VacationEntry, site=custom_admin_site)
class VacationEntryAdmin(admin.ModelAdmin):
    list_display = ["start_date", "end_date", "profile", "notes"]
    list_filter = ["start_date", "profile"]
    search_fields = ["profile__title", "notes"]
