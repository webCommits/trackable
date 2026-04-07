from django.contrib import admin
from trackable.profiles.models import Profile
from trackable.core.admin_site import custom_admin_site


@admin.register(Profile, site=custom_admin_site)
class ProfileAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "position",
        "weekly_hours",
        "hourly_rate",
        "user",
        "created_at",
    ]
    list_filter = ["created_at", "user"]
    search_fields = ["title", "position", "internal_notes"]
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "user",
                    "title",
                    "position",
                    "address",
                    "weekly_hours",
                    "hourly_rate",
                ]
            },
        ),
        ("Internal", {"fields": ["internal_notes"], "classes": ["collapse"]}),
    ]
    list_filter = ["created_at", "user"]
    search_fields = ["title", "position", "internal_notes"]
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "user",
                    "title",
                    "position",
                    "address",
                    "weekly_hours",
                    "hourly_rate",
                ]
            },
        ),
        ("Internal", {"fields": ["internal_notes"], "classes": ["collapse"]}),
    ]
