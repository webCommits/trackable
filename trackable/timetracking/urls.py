from django.urls import path
from . import views

urlpatterns = [
    path("app/", views.home, name="home"),
    path("add-entry/<int:profile_id>/", views.add_entry, name="add_entry"),
    path("entry/<int:pk>/edit/", views.edit_entry, name="edit_entry"),
    path("entry/<int:pk>/delete/", views.delete_entry, name="delete_entry"),
    path(
        "table/<int:profile_id>/<int:year>/<int:month>/",
        views.monthly_table,
        name="monthly_table",
    ),
    path(
        "export/<int:profile_id>/<int:year>/<int:month>/",
        views.export_pdf,
        name="export_pdf",
    ),
    path(
        "export-csv/<int:profile_id>/<int:year>/<int:month>/",
        views.export_csv,
        name="export_csv",
    ),
    path(
        "vacation/<int:profile_id>/", views.vacation_overview, name="vacation_overview"
    ),
    path("vacation/<int:profile_id>/add/", views.add_vacation, name="add_vacation"),
    path("vacation/delete/<int:pk>/", views.delete_vacation, name="delete_vacation"),
    path("timer/<int:profile_id>/start/", views.start_timer, name="start_timer"),
    path("timer/<int:profile_id>/pause/", views.pause_timer, name="pause_timer"),
    path("timer/<int:profile_id>/resume/", views.resume_timer, name="resume_timer"),
    path("timer/<int:profile_id>/stop/", views.stop_timer, name="stop_timer"),
    path("timer/<int:profile_id>/status/", views.timer_status, name="timer_status"),
]
