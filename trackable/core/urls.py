from django.urls import path
from . import views
from . import setup_views
from . import manage_views

urlpatterns = [
    path("",             views.landing,     name="landing"),
    path("impressum/",   views.impressum,   name="impressum"),
    path("datenschutz/", views.datenschutz, name="datenschutz"),
    path("set-language/", views.set_language, name="set_language"),
    path("setup/",         setup_views.setup_step1, name="setup_step1"),
    path("setup/step2/",   setup_views.setup_step2, name="setup_step2"),
    path("setup/done/",    setup_views.setup_done,  name="setup_done"),
    path("manage/",                    manage_views.manage_dashboard, name="manage_dashboard"),
    path("manage/settings/",           manage_views.manage_settings,  name="manage_settings"),
    path("manage/reset-setup/",        manage_views.manage_reset_setup, name="manage_reset_setup"),
    path("manage/users/",              manage_views.manage_user_list,   name="manage_user_list"),
    path("manage/users/create/",       manage_views.manage_user_create, name="manage_user_create"),
    path("manage/users/<int:user_id>/", manage_views.manage_user_detail, name="manage_user_detail"),
]
