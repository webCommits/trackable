from django.contrib import admin
from trackable.core.models import Holiday


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ["date", "name"]
    list_filter = ["date"]
    search_fields = ["name"]
    ordering = ["date"]
