from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from trackable.accounts.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "email_notifications_enabled", "is_staff"]
    list_filter = ["email_notifications_enabled", "is_staff", "is_superuser"]
    search_fields = ["username", "email"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Trackable", {"fields": ("email_notifications_enabled",)}),
    )
