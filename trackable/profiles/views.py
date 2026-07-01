from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from trackable.organizations.helpers import can_edit_time_entries
from trackable.profiles.forms import ProfileForm
from trackable.profiles.models import Profile


@login_required
def profile_list(request):
    profiles = request.user.profiles.all()
    return render(request, "profiles/list.html", {"profiles": profiles})


@login_required
def profile_create(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, user=request.user)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            messages.success(request, _('Profile "%(title)s" was created successfully!') % {"title": profile.title})
            return redirect("profile_detail", pk=profile.pk)
    else:
        form = ProfileForm(user=request.user)
    return render(request, "profiles/create.html", {"form": form})


@login_required
def profile_detail(request, pk):
    profile = get_object_or_404(Profile, pk=pk, user=request.user)

    from datetime import datetime, timedelta
    from trackable.timetracking.models import ENTRY_TYPE_ACTUAL

    current_date = timezone.now().date()

    # ── Weekly calendar ──
    # Calculate current ISO week (Monday–Sunday)
    iso = current_date.isocalendar()
    monday = datetime.fromisocalendar(iso[0], iso[1], 1).date()
    week_days = []
    for i in range(7):
        day = monday + timedelta(days=i)
        day_entries = profile.time_entries.filter(date=day, entry_type=ENTRY_TYPE_ACTUAL)
        total_hours = sum(
            (float(e.hours_worked) for e in day_entries)
        )
        week_days.append({
            "date": day,
            "day_name": day.strftime("%a"),
            "day_number": day.day,
            "month_name": day.strftime("%b"),
            "is_today": day == current_date,
            "is_past": day < current_date,
            "total_hours": total_hours,
            "entry_count": day_entries.count(),
        })
    week_total = sum(d["total_hours"] for d in week_days)
    has_org = request.user.is_org_member

    can_log_time = can_edit_time_entries(request.user)

    membership = getattr(request.user, "organization_membership", None)
    show_vacation = True
    if membership:
        show_vacation = membership.organization.holidays_enabled

    # ── Monthly overview ──
    months = profile.get_monthly_account_rows(
        until_year=current_date.year,
        until_month=current_date.month,
    )

    return render(request, "profiles/detail.html", {
        "profile": profile,
        "months": months,
        "week_days": week_days,
        "week_total": week_total,
        "week_monday": monday,
        "has_org": has_org,
        "can_log_time": can_log_time,
        "show_vacation": show_vacation,
    })


@login_required
def profile_edit(request, pk):
    profile = get_object_or_404(Profile, pk=pk, user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Profile was updated successfully!"))
            return redirect("profile_detail", pk=profile.pk)
    else:
        form = ProfileForm(instance=profile, user=request.user)
    return render(request, "profiles/create.html", {"form": form, "edit": True, "profile": profile})


@login_required
def profile_delete(request, pk):
    profile = get_object_or_404(Profile, pk=pk, user=request.user)
    if request.method == "POST":
        profile.delete()
        messages.success(request, _("Profile was deleted."))
        return redirect("profile_list")
    return redirect("profile_detail", pk=pk)
