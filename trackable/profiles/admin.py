from django.contrib import admin
from trackable.profiles.models import Profile


@admin.register(Profile)
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
    search_fields = ["title", "position"]
