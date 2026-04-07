from django.contrib import admin
from trackable.core.models import Holiday
from trackable.core.admin_site import custom_admin_site


@admin.register(Holiday, site=custom_admin_site)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ["date", "name", "organization"]
    list_filter = ["date", "organization"]
    search_fields = ["name"]
    ordering = ["date"]
