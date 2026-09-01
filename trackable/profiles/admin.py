from django.contrib import admin
from trackable.profiles.models import Profile, TargetHoursChange
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
        "archived_at",
    ]
    list_filter = ["created_at", "archived_at", "user"]
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


@admin.register(TargetHoursChange, site=custom_admin_site)
class TargetHoursChangeAdmin(admin.ModelAdmin):
    list_display = [
        "profile",
        "valid_from",
        "target_hours_period",
        "weekly_hours",
        "weekly_target_hours",
        "monthly_target_hours",
    ]
    list_filter = ["target_hours_period"]
    search_fields = ["profile__title", "profile__position"]
