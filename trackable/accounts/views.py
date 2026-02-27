from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib import messages
from django.urls import reverse_lazy
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import html2text
from trackable.accounts.forms import UserRegistrationForm
from trackable.accounts.models import User


class CustomLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class CustomLogoutView(LogoutView):
    next_page = reverse_lazy("login")


def register(request):
    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get("username")
            messages.success(
                request, f"Account für {username} wurde erfolgreich erstellt!"
            )
            login(request, user)
            return redirect("home")
    else:
        form = UserRegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


def password_reset_request(request):
    if request.method == "POST":
        email = request.POST.get("email")
        try:
            user = User.objects.get(email=email)
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))

            reset_url = request.build_absolute_uri(f"/accounts/reset/{uid}/{token}/")

            html_message = render_to_string(
                "emails/password_reset_email.html",
                {
                    "user": user,
                    "reset_url": reset_url,
                },
            )

            text_message = html2text.html2text(html_message)

            send_mail(
                "Passwort zurücksetzen - Trackable",
                text_message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                html_message=html_message,
                fail_silently=False,
            )

            messages.success(
                request, "Passwort-Reset-Link wurde an Ihre E-Mail gesendet."
            )
        except User.DoesNotExist:
            messages.error(request, "Kein Benutzer mit dieser E-Mail gefunden.")

        return redirect("password_reset_request")

    return render(request, "accounts/password_reset.html")


def password_reset_confirm(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except:
        user = None

    if user and default_token_generator.check_token(user, token):
        if request.method == "POST":
            password = request.POST.get("password")
            password_confirm = request.POST.get("password_confirm")

            if password and password_confirm and password == password_confirm:
                user.set_password(password)
                user.save()
                messages.success(
                    request, "Ihr Passwort wurde erfolgreich zurückgesetzt."
                )
                return redirect("login")
            else:
                messages.error(request, "Die Passwörter stimmen nicht überein.")

        return render(
            request,
            "accounts/password_reset_confirm.html",
            {
                "validlink": True,
                "uidb64": uidb64,
                "token": token,
            },
        )

    messages.error(request, "Der Reset-Link ist ungültig oder abgelaufen.")
    return redirect("password_reset_request")


@login_required
def profile_settings(request):
    if request.method == "POST":
        user = request.user
        user.email_notifications_enabled = (
            request.POST.get("email_notifications_enabled") == "on"
        )
        user.save()
        messages.success(request, "Einstellungen wurden gespeichert.")
        return redirect("home")

    return render(
        request,
        "accounts/settings.html",
        {
            "user": request.user,
        },
    )
