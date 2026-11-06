import secrets

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import redirect_to_login
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from trackable.core.models import SiteConfiguration
from trackable.accounts.models import User


def setup_step1(request):
    """Step 1: Create the admin account."""
    config = SiteConfiguration.get()
    if config.setup_completed:
        return redirect("login")

    # Optional shared secret gate (SETUP_TOKEN env var). If unset, behaves
    # exactly as before. If set, the whole step (including the "admin
    # already exists" info page below) requires the correct token on both
    # GET (query string) and POST (hidden form field), so an attacker can't
    # even observe setup state without it.
    setup_token = getattr(settings, "SETUP_TOKEN", "")
    if setup_token:
        token = request.POST.get("token", "") if request.method == "POST" else request.GET.get("token", "")
        if not secrets.compare_digest(token, setup_token):
            return render(request, "core/setup/token_required.html", status=403)
    else:
        token = ""

    # If superuser already exists (e.g., created via CLI), show info page
    if User.objects.filter(is_superuser=True).exists():
        return render(request, "core/setup/admin_exists.html")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        password_confirm = request.POST.get("password_confirm", "")

        errors = []
        if not username:
            errors.append(_("Username is required."))
        if not email:
            errors.append(_("Email is required."))
        if not password:
            errors.append(_("Password is required."))
        elif password != password_confirm:
            errors.append(_("Passwords do not match."))
        else:
            try:
                validate_password(password)
            except ValidationError as e:
                errors.extend(e.messages)

        if User.objects.filter(username=username).exists():
            errors.append(_("Username is already taken."))
        if email and User.objects.filter(email=email).exists():
            errors.append(_("Email is already in use."))

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, "core/setup/step1.html", {"token": token})

        user = User.objects.create(
            username=username,
            email=email,
            is_superuser=True,
            is_staff=True,
            is_active=True,
            email_confirmed=True,
        )
        user.set_password(password)
        user.save()

        # Auto-login the admin
        login(request, user)
        messages.success(request, _("Admin account created! Now configure your settings."))
        return redirect("setup_step2")

    return render(request, "core/setup/step1.html", {"token": token})


def setup_step2(request):
    """Step 2: Configure site settings and email."""
    config = SiteConfiguration.get()
    if config.setup_completed:
        return redirect("login")

    # Only an authenticated superuser may view or complete this step —
    # otherwise anyone could (re)configure SMTP credentials, allowed hosts,
    # and registration settings before an admin even logs in.
    if not (request.user.is_authenticated and request.user.is_superuser):
        return redirect_to_login(request.get_full_path())

    if not User.objects.filter(is_superuser=True).exists():
        return redirect("setup_step1")

    if request.method == "POST":
        config.registration_enabled = request.POST.get("registration_enabled") == "on"
        
        # Email settings (optional — leave empty to use env var defaults)
        email_host = request.POST.get("email_host", "").strip()
        config.email_host = email_host
        
        email_port_str = request.POST.get("email_port", "").strip()
        if email_port_str:
            try:
                config.email_port = int(email_port_str)
            except (ValueError, TypeError):
                pass
        else:
            config.email_port = 587
        
        config.email_use_tls = request.POST.get("email_use_tls") == "on"
        config.email_host_user = request.POST.get("email_host_user", "").strip()
        config.email_host_password = request.POST.get("email_host_password", "").strip()
        config.default_from_email = request.POST.get("default_from_email", "").strip()
        config.allowed_hosts = request.POST.get("allowed_hosts", "").strip()
        config.setup_completed = True
        config.save()
        
        messages.success(request, _("Setup complete! You can now log in to trackable."))
        return redirect("setup_done")
    
    return render(request, "core/setup/step2.html", {
        "config": config,
    })


def setup_done(request):
    """Setup complete page."""
    config = SiteConfiguration.get()
    if not config.setup_completed:
        return redirect("setup_step1")
    
    return render(request, "core/setup/done.html")
