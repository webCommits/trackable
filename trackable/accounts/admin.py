from django.contrib import admin
from trackable.accounts.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["username", "email", "email_notifications_enabled", "is_staff"]
    list_filter = ["email_notifications_enabled", "is_staff", "is_superuser"]
    search_fields = ["username", "email"]
