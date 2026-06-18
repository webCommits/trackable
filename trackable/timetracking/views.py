from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext as _g
from datetime import datetime, timedelta
import calendar
import csv
from datetime import time as time_obj
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from trackable.timetracking.forms import TimeEntryForm, VacationEntryForm
from trackable.timetracking.models import TimeEntry, VacationEntry, ActiveTimer
from trackable.profiles.models import Profile
from trackable.organizations.helpers import (
    can_edit_time_entries,
    can_manage_profile_time_entries,
    can_manage_time_entry,
    is_org_manager,
)


@login_required
def home(request):
    profiles = request.user.profiles.all()
    active_timers = {
        timer.profile_id: timer
        for timer in ActiveTimer.objects.filter(user=request.user).select_related(
            "profile"
        )
    }
    has_org = hasattr(request.user, "organization_membership")
    can_edit = can_edit_time_entries(request.user)
    if profiles.count() == 0:
        return redirect("profile_create")
    return render(
        request,
        "timetracking/home.html",
        {
            "profiles": profiles,
            "active_timers": active_timers,
            "has_org": has_org,
            "can_edit": can_edit,
        },
    )


@login_required
def add_entry(request, profile_id):
    profile = get_object_or_404(Profile, pk=profile_id)

    if not can_manage_profile_time_entries(request.user, profile):
        messages.error(request, _("You do not have permission to add time entries for this profile."))
        return redirect("home")

    if request.method == "POST":
        form = TimeEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.profile = profile
            entry.save()
            messages.success(
                request,
                _("Time entry for %(date)s was saved successfully!")
                % {"date": entry.date},
            )
            if is_org_manager(request.user) and profile.user != request.user:
                return redirect(
                    "employee_profile_detail",
                    user_id=profile.user_id,
                    profile_id=profile.pk,
                )
            return redirect("profile_detail", pk=profile.pk)
    else:
        form = TimeEntryForm()
    return render(
        request, "timetracking/add_entry.html", {"form": form, "profile": profile}
    )


@login_required
def edit_entry(request, pk):
    entry = get_object_or_404(TimeEntry, pk=pk)
    profile = entry.profile

    if not can_manage_time_entry(request.user, entry):
        messages.error(request, _("You do not have permission to edit this time entry."))
        return redirect("home")

    if request.method == "POST":
        form = TimeEntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            messages.success(request, _("Time entry was updated successfully!"))
            if is_org_manager(request.user) and profile.user != request.user:
                return redirect(
                    "employee_profile_detail",
                    user_id=profile.user_id,
                    profile_id=profile.pk,
                )
            return redirect(
                "monthly_table",
                profile_id=profile.pk,
                year=entry.date.year,
                month=entry.date.month,
            )
    else:
        form = TimeEntryForm(instance=entry)
    return render(
        request,
        "timetracking/add_entry.html",
        {"form": form, "profile": profile, "edit": True},
    )


@login_required
def delete_entry(request, pk):
    entry = get_object_or_404(TimeEntry, pk=pk)

    if not can_manage_time_entry(request.user, entry):
        messages.error(request, _("You do not have permission to delete this time entry."))
        return redirect("home")

    year, month = entry.date.year, entry.date.month
    profile_id = entry.profile_id
    user_id = entry.profile.user_id
    if request.method == "POST":
        entry.delete()
        messages.success(request, _("Time entry was deleted."))

    if is_org_manager(request.user) and user_id != request.user.id:
        return redirect(
            "employee_profile_detail",
            user_id=user_id,
            profile_id=profile_id,
        )
    return redirect("monthly_table", profile_id=profile_id, year=year, month=month)


@login_required
def monthly_table(request, profile_id, year, month):
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)
    time_entries = list(profile.get_monthly_entries(year, month).order_by("date"))
    last_day = calendar.monthrange(year, month)[1]
    vacation_entries = list(
        profile.vacation_entries.filter(
            start_date__lte=datetime(year, month, last_day).date(),
            end_date__gte=datetime(year, month, 1).date(),
        ).order_by("start_date")
    )
    total_hours = profile.get_monthly_hours(year, month)
    total_earnings = profile.get_monthly_earnings(year, month)
    target_hours = profile.get_target_hours(year, month)
    balance = profile.get_balance(year, month)
    total_vacation_days = sum(v.workdays for v in vacation_entries)
    month_name = datetime(year, month, 1).strftime("%B %Y")

    # Show edit/delete actions?
    show_actions = can_edit_time_entries(request.user)

    membership = getattr(request.user, "organization_membership", None)
    show_vacation = True
    if membership:
        show_vacation = membership.organization.holidays_enabled

    return render(
        request,
        "timetracking/monthly_table.html",
        {
            "profile": profile,
            "time_entries": time_entries,
            "vacation_entries": vacation_entries,
            "year": year,
            "month": month,
            "month_name": month_name,
            "total_hours": total_hours,
            "total_earnings": total_earnings,
            "target_hours": target_hours,
            "balance": balance,
            "total_vacation_days": total_vacation_days,
            "show_actions": show_actions,
            "show_vacation": show_vacation,
        },
    )


# ── Vacation ──────────────────────────────────────────────────────────────────


@login_required
def add_vacation(request, profile_id):
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)

    membership = getattr(request.user, "organization_membership", None)
    if membership and not membership.organization.holidays_enabled:
        messages.error(request, _("Vacation tracking is disabled for your organization."))
        return redirect("home")

    if request.method == "POST":
        form = VacationEntryForm(request.POST)
        if form.is_valid():
            vacation = form.save(commit=False)
            vacation.profile = profile
            if vacation.end_date < vacation.start_date:
                form.add_error("end_date", _("End date must be after start date."))
            else:
                vacation.save()
                messages.success(request, _("Vacation entry was saved successfully!"))
                return redirect("vacation_overview", profile_id=profile.pk)
    else:
        form = VacationEntryForm()
    return render(
        request, "timetracking/add_vacation.html", {"form": form, "profile": profile}
    )


@login_required
def delete_vacation(request, pk):
    vacation = get_object_or_404(VacationEntry, pk=pk, profile__user=request.user)

    membership = getattr(request.user, "organization_membership", None)
    if membership and not membership.organization.holidays_enabled:
        messages.error(request, _("Vacation tracking is disabled for your organization."))
        return redirect("home")

    profile_id = vacation.profile_id
    if request.method == "POST":
        vacation.delete()
        messages.success(request, _("Vacation entry was deleted."))
    return redirect("vacation_overview", profile_id=profile_id)


@login_required
def vacation_overview(request, profile_id):
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)

    membership = getattr(request.user, "organization_membership", None)
    if membership and not membership.organization.holidays_enabled:
        messages.error(request, _("Vacation tracking is disabled for your organization."))
        return redirect("home")

    from django.utils.timezone import now

    current_year = now().year
    year = int(request.GET.get("year", current_year))
    vacations = (
        (
            profile.vacation_entries.filter(start_date__year=year)
            | profile.vacation_entries.filter(end_date__year=year)
        )
        .distinct()
        .order_by("start_date")
    )
    total_days = sum(v.workdays for v in vacations)
    year_range = range(current_year - 2, current_year + 2)
    return render(
        request,
        "timetracking/vacation_overview.html",
        {
            "profile": profile,
            "vacations": vacations,
            "year": year,
            "year_range": year_range,
            "total_days": total_days,
        },
    )


# ── PDF Export ────────────────────────────────────────────────────────────────


@login_required
def export_pdf(request, profile_id, year, month):
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)
    from trackable.core.pdf_export import generate_pdf_report

    buffer = generate_pdf_report(profile, year, month)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="arbeitszeiten_{profile.title}_{year}_{month}.pdf"'
    )
    response.write(buffer.getvalue())
    buffer.close()

    return response


# ── Timer API Endpoints ───────────────────────────────────────────────────────


def _parse_client_timestamp(request):
    """
    Parse optional client_timestamp from request body (JSON or form).
    Returns a timezone-aware datetime or None.
    """
    import json
    from datetime import datetime

    ts_str = None
    if request.content_type == "application/json":
        try:
            body = json.loads(request.body)
            ts_str = body.get("client_timestamp")
        except (ValueError, AttributeError):
            pass
    else:
        ts_str = request.POST.get("client_timestamp")

    if not ts_str:
        return None

    try:
        from datetime import timezone as dt_timezone
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(ts_str)
        if dt is None:
            return None
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        # Normalize to UTC so all timer math is consistent
        # (ActiveTimer.start_time is stored as UTC by Django)
        dt = dt.astimezone(dt_timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


@login_required
@require_http_methods(["POST"])
def start_timer(request, profile_id):
    """Start a timer for a profile.

    Accepts optional client_timestamp (ISO 8601) so queued offline
    starts record the correct start time.
    """
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)

    existing_timer = ActiveTimer.objects.filter(
        profile=profile, user=request.user
    ).first()
    if existing_timer:
        return JsonResponse(
            {"error": "Timer already running for this profile"}, status=400
        )

    client_ts = _parse_client_timestamp(request)
    start_time = client_ts or timezone.now()

    timer = ActiveTimer.objects.create(
        profile=profile, user=request.user, start_time=start_time, is_paused=False
    )

    return JsonResponse(
        {
            "status": "started",
            "start_time": timer.start_time.isoformat(),
            "profile_id": profile.id,
            "profile_title": profile.title,
        }
    )


@login_required
@require_http_methods(["POST"])
def pause_timer(request, profile_id):
    """Pause a running timer.

    Accepts optional client_timestamp so queued offline pauses
    record the correct pause time.
    """
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)

    timer = ActiveTimer.objects.filter(profile=profile, user=request.user).first()
    if not timer:
        return JsonResponse({"error": "No active timer found"}, status=404)

    if timer.is_paused:
        return JsonResponse({"error": "Timer is already paused"}, status=400)

    client_ts = _parse_client_timestamp(request)
    timer.pause_time = client_ts or timezone.now()
    timer.is_paused = True
    timer.save()

    return JsonResponse(
        {
            "status": "paused",
            "pause_time": timer.pause_time.isoformat(),
            "total_paused_seconds": timer.total_paused_seconds,
        }
    )


@login_required
@require_http_methods(["POST"])
def resume_timer(request, profile_id):
    """Resume a paused timer.

    Accepts optional client_timestamp so queued offline resumes
    calculate the correct pause duration.
    """
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)

    timer = ActiveTimer.objects.filter(profile=profile, user=request.user).first()
    if not timer:
        return JsonResponse({"error": "No active timer found"}, status=404)

    if not timer.is_paused:
        return JsonResponse({"error": "Timer is not paused"}, status=400)

    client_ts = _parse_client_timestamp(request)
    resume_time = client_ts or timezone.now()
    paused_duration = int((resume_time - timer.pause_time).total_seconds())
    timer.total_paused_seconds += max(0, paused_duration)
    timer.pause_time = None
    timer.is_paused = False
    timer.save()

    return JsonResponse(
        {"status": "resumed", "total_paused_seconds": timer.total_paused_seconds}
    )


@login_required
@require_http_methods(["POST"])
def stop_timer(request, profile_id):
    """Stop timer and create TimeEntry.

    Accepts optional client_timestamp so queued offline stops
    record the correct end time and duration.
    """
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)

    timer = ActiveTimer.objects.filter(profile=profile, user=request.user).first()
    if not timer:
        return JsonResponse({"error": "No active timer found"}, status=404)

    client_ts = _parse_client_timestamp(request)
    stop_time = client_ts or timezone.now()

    total_seconds = (
        stop_time - timer.start_time
    ).total_seconds() - timer.total_paused_seconds

    if total_seconds < 0:
        total_seconds = 0

    hours_worked = total_seconds / 3600

    entry_date = timer.start_time.date()
    start_time_obj = timer.start_time.time()
    end_time_obj = stop_time.time()

    time_entry = TimeEntry.objects.create(
        profile=profile,
        date=entry_date,
        start_time=start_time_obj,
        end_time=end_time_obj,
        pause_duration=round(timer.total_paused_seconds / 3600, 2),
        hours_worked=round(hours_worked, 2),
    )

    timer.delete()

    return JsonResponse(
        {
            "status": "stopped",
            "hours_worked": round(hours_worked, 2),
            "entry_id": time_entry.id,
            "date": str(entry_date),
            "message": f"Time entry created: {round(hours_worked, 2)} hours",
        }
    )


@login_required
def timer_status(request, profile_id):
    """Get current timer status for a profile."""
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)

    timer = ActiveTimer.objects.filter(profile=profile, user=request.user).first()
    if not timer:
        return JsonResponse({"has_timer": False})

    now = timezone.now()
    if timer.is_paused:
        elapsed_seconds = (
            timer.pause_time - timer.start_time
        ).total_seconds() - timer.total_paused_seconds
    else:
        elapsed_seconds = (
            now - timer.start_time
        ).total_seconds() - timer.total_paused_seconds

    return JsonResponse(
        {
            "has_timer": True,
            "is_paused": timer.is_paused,
            "start_time": timer.start_time.isoformat(),
            "elapsed_seconds": int(elapsed_seconds),
            "total_paused_seconds": timer.total_paused_seconds,
        }
    )


# ── CSV Export ────────────────────────────────────────────────────────────────


@login_required
def export_csv(request, profile_id, year, month):
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)
    time_entries = list(profile.get_monthly_entries(year, month).order_by("date"))

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="arbeitszeiten_{profile.title}_{year}_{month}.csv"'
    )
    response.write("\ufeff")  # BOM for Excel compatibility

    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            _g("Date"),
            _g("Start"),
            _g("End"),
            _g("Break") + " (h)",
            _g("Hours"),
            _g("Activity"),
        ]
    )
    for entry in time_entries:
        writer.writerow(
            [
                entry.date.strftime("%d.%m.%Y"),
                entry.start_time.strftime("%H:%M"),
                entry.end_time.strftime("%H:%M"),
                str(entry.pause_duration).replace(".", ","),
                str(round(entry.hours_worked, 2)).replace(".", ","),
                entry.notes or "",
            ]
        )
    return response
