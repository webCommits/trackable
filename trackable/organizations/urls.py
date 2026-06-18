from django.urls import path
from . import views
from . import import_views

urlpatterns = [
    path("", views.org_dashboard, name="org_dashboard"),
    path("create/", views.org_create, name="org_create"),
    path("employees/create/", views.employee_create, name="employee_create"),
    path("employees/<int:user_id>/", views.employee_detail, name="employee_detail"),
    path(
        "employees/<int:user_id>/profiles/<int:profile_id>/",
        views.employee_profile_detail,
        name="employee_profile_detail",
    ),
    path(
        "employees/<int:user_id>/profiles/<int:profile_id>/set-target-hours/",
        views.set_target_hours,
        name="set_target_hours",
    ),
    path(
        "employees/<int:user_id>/profiles/<int:profile_id>/set-contract-dates/",
        views.set_contract_dates,
        name="set_contract_dates",
    ),
    path(
        "employees/<int:user_id>/remove/", views.employee_remove, name="employee_remove"
    ),
    path("weekly/", views.org_weekly_calendar, name="org_weekly_calendar"),
    path("weekly/create-entry/", views.create_entry, name="create_entry"),
    path("weekly/update-entry/<int:entry_id>/", views.update_entry, name="update_entry"),
    path("weekly/move-entry/<int:entry_id>/", views.move_entry, name="move_entry"),
    path("weekly/delete-entry/<int:entry_id>/", views.delete_calendar_entry, name="delete_calendar_entry"),
    path("toggle-time-tracking-mode/", views.toggle_time_tracking_mode, name="toggle_time_tracking_mode"),
    path("toggle-holidays/", views.toggle_holidays, name="toggle_holidays"),
    path("holidays/", views.holiday_list, name="org_holidays"),
    path("holidays/add/", views.holiday_create, name="org_holiday_add"),
    path("holidays/<int:pk>/delete/", views.holiday_delete, name="org_holiday_delete"),

    # Time entry import
    path("import-time-entries/", import_views.time_entry_import, name="time_entry_import"),
    path(
        "import-time-entries/confirm/",
        import_views.time_entry_import_confirm,
        name="time_entry_import_confirm",
    ),
    # Branding
    path("branding/", views.org_branding, name="org_branding"),
]
