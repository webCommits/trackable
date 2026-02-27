from django.urls import path
from . import views

urlpatterns = [
    path("app/", views.home, name="home"),
    path("add-entry/<int:profile_id>/", views.add_entry, name="add_entry"),
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
]
