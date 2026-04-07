from django.urls import path
from . import views

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
        "employees/<int:user_id>/remove/", views.employee_remove, name="employee_remove"
    ),
    path("holidays/", views.holiday_list, name="org_holidays"),
    path("holidays/add/", views.holiday_create, name="org_holiday_add"),
    path("holidays/<int:pk>/delete/", views.holiday_delete, name="org_holiday_delete"),
]
