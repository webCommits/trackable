from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth.models import Group, User as AuthUser
from django.contrib.auth.admin import (
    GroupAdmin as BaseGroupAdmin,
    UserAdmin as BaseAuthUserAdmin,
)
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class TrackableAdminSite(AdminSite):
    site_header = "Trackable Admin"
    site_title = "Trackable Admin"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "email-test/", self.admin_view(self.email_test_view), name="email_test"
            ),
        ]
        return custom_urls + urls

    def email_test_view(self, request):
        if request.method == "POST":
            recipient = request.POST.get("recipient", "").strip()
            if not recipient:
                messages.error(request, _("Please enter a recipient email address."))
            else:
                try:
                    send_mail(
                        _("Trackable – Test Email"),
                        _(
                            "This is a test email from your Trackable instance.\n\n"
                            "If you received this email, your email configuration is working correctly."
                        ),
                        settings.DEFAULT_FROM_EMAIL,
                        [recipient],
                        fail_silently=False,
                    )
                    messages.success(
                        request,
                        _("Test email sent successfully to %(email)s!")
                        % {"email": recipient},
                    )
                except Exception as e:
                    messages.error(
                        request,
                        _("Failed to send email: %(error)s") % {"error": str(e)},
                    )
            return redirect("admin:email_test")

        return render(
            request,
            "admin/email_test.html",
            {
                "title": _("Email Test"),
                "email_backend": settings.EMAIL_BACKEND,
                "email_host": settings.EMAIL_HOST,
                "email_port": settings.EMAIL_PORT,
                "email_use_tls": settings.EMAIL_USE_TLS,
                "default_from_email": settings.DEFAULT_FROM_EMAIL,
            },
        )


custom_admin_site = TrackableAdminSite(name="admin")

custom_admin_site.register(AuthUser, BaseAuthUserAdmin)
custom_admin_site.register(Group, BaseGroupAdmin)
