from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from trackable.organizations.helpers import can_edit_time_entries
from trackable.profiles.forms import ProfileForm
from trackable.profiles.models import Profile


@login_required
def profile_list(request):
    profiles = request.user.profiles.filter(archived_at__isnull=True)
    archived_profiles = request.user.profiles.filter(archived_at__isnull=False)
    return render(
        request,
        "profiles/list.html",
        {"profiles": profiles, "archived_profiles": archived_profiles},
    )


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

    target_hours_changes = profile.target_hours_changes.order_by(
        F("valid_from").asc(nulls_first=True)
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
        "target_hours_changes": target_hours_changes,
    })


@login_required
def profile_edit(request, pk):
    profile = get_object_or_404(Profile, pk=pk, user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile, user=request.user)
        if form.is_valid():
            old_period = profile.target_hours_period
            old_weekly_hours = profile.weekly_hours
            old_weekly_target_hours = profile.weekly_target_hours
            old_monthly_target_hours = profile.monthly_target_hours

            instance = form.save(commit=False)
            valid_from = form.cleaned_data.get("target_hours_valid_from")
            new_period = instance.target_hours_period
            new_weekly_hours = instance.weekly_hours
            new_weekly_target_hours = instance.weekly_target_hours
            new_monthly_target_hours = instance.monthly_target_hours

            target_hours_changed = (
                new_period != old_period
                or new_weekly_hours != old_weekly_hours
                or new_weekly_target_hours != old_weekly_target_hours
                or new_monthly_target_hours != old_monthly_target_hours
            )

            if target_hours_changed:
                # Persist non-target-hours changes first, keeping the
                # target-hours fields at their old values; the history-aware
                # write path below applies the new target-hours values
                # (valid_from=None means retroactive: clears history and
                # writes the fields directly, matching the pre-existing
                # behavior).
                instance.target_hours_period = old_period
                instance.weekly_hours = old_weekly_hours
                instance.weekly_target_hours = old_weekly_target_hours
                instance.monthly_target_hours = old_monthly_target_hours
                with transaction.atomic():
                    instance.save()
                    profile.apply_target_hours_change(
                        period=new_period,
                        weekly_hours=new_weekly_hours,
                        weekly_target_hours=new_weekly_target_hours,
                        monthly_target_hours=new_monthly_target_hours,
                        valid_from=valid_from,
                    )
            else:
                instance.save()

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


@login_required
def profile_archive(request, pk):
    profile = get_object_or_404(Profile, pk=pk, user=request.user)
    if request.method == "POST":
        profile.archived_at = timezone.now()
        profile.save()
        messages.success(request, _("Profile was archived."))
        return redirect("profile_list")
    return redirect("profile_detail", pk=pk)


@login_required
def profile_unarchive(request, pk):
    profile = get_object_or_404(Profile, pk=pk, user=request.user)
    if request.method == "POST":
        profile.archived_at = None
        profile.save()
        messages.success(request, _("Profile was unarchived."))
        return redirect("profile_detail", pk=pk)
    return redirect("profile_detail", pk=pk)
