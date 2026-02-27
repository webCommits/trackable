from django.urls import path
from . import views

urlpatterns = [
    path("",             views.landing,     name="landing"),
    path("impressum/",   views.impressum,   name="impressum"),
    path("datenschutz/", views.datenschutz, name="datenschutz"),
]
