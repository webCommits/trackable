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
import json
from datetime import time as time_obj
from datetime import date as date_obj
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import IntegrityError, transaction
from trackable.timetracking.forms import TimeEntryForm, VacationEntryForm
from trackable.timetracking.models import TimeEntry, VacationEntry, ActiveTimer
from trackable.profiles.models import Profile
from trackable.organizations.helpers import (
    can_edit_time_entries,
    can_manage_profile_time_entries,
    can_manage_time_entry,
    is_org_manager,
)

NOTES_MAX_LENGTH = 1000



@login_required
def home(request):
    all_profiles = request.user.profiles.all()
    profiles = all_profiles.filter(archived_at__isnull=True)
    has_archived = all_profiles.filter(archived_at__isnull=False).exists()
    active_timers = {
        timer.profile_id: timer
        for timer in ActiveTimer.objects.filter(user=request.user).select_related(
            "profile"
        )
    }
    has_org = hasattr(request.user, "organization_membership")
    can_edit = can_edit_time_entries(request.user)
    if all_profiles.count() == 0:
        return redirect("profile_create")
    return render(
        request,
        "timetracking/home.html",
        {
            "profiles": profiles,
            "active_timers": active_timers,
            "has_org": has_org,
            "can_edit": can_edit,
            "has_archived": has_archived,
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
    cumulative_balance = profile.get_cumulative_balance(year, month)
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
            "cumulative_balance": cumulative_balance,
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
    Future timestamps are clamped to timezone.now().
    """
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
        # Clamp future timestamps to now to prevent future start/pause/stop
        now = timezone.now()
        if dt > now:
            dt = now
        return dt
    except (ValueError, TypeError):
        return None


@login_required
@require_http_methods(["POST"])
def start_timer(request, profile_id):
    """Start a timer for a profile.

    Accepts optional client_timestamp (ISO 8601) so queued offline
    starts record the correct start time.
    Uses select_for_update + atomic to prevent race conditions.
    IntegrityError is caught and returns 400 instead of 500.
    """
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)

    client_ts = _parse_client_timestamp(request)
    start_time = client_ts or timezone.now()

    try:
        with transaction.atomic():
            existing_timer = ActiveTimer.objects.select_for_update().filter(
                profile=profile, user=request.user
            ).first()
            if existing_timer:
                return JsonResponse(
                    {"error": "Timer already running for this profile"}, status=400
                )
            timer = ActiveTimer.objects.create(
                profile=profile, user=request.user, start_time=start_time, is_paused=False
            )
    except IntegrityError:
        return JsonResponse(
            {"error": "Timer already running for this profile"}, status=400
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

    with transaction.atomic():
        timer = ActiveTimer.objects.select_for_update().filter(
            profile=profile, user=request.user
        ).first()
        if not timer:
            return JsonResponse({"error": "No active timer found"}, status=404)

        if timer.is_paused:
            return JsonResponse({"error": "Timer is already paused"}, status=400)

        client_ts = _parse_client_timestamp(request)
        timer.pause_time = client_ts or timezone.now()
        # Clamp pause_time to start_time to prevent negative pause durations
        # when client_timestamp is before the timer started (offline queue).
        if timer.pause_time < timer.start_time:
            timer.pause_time = timer.start_time
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

    with transaction.atomic():
        timer = ActiveTimer.objects.select_for_update().filter(
            profile=profile, user=request.user
        ).first()
        if not timer:
            return JsonResponse({"error": "No active timer found"}, status=404)

        if not timer.is_paused:
            return JsonResponse({"error": "Timer is not paused"}, status=400)

        if not timer.pause_time:
            return JsonResponse({"error": "Paused timer has no pause time"}, status=400)

        client_ts = _parse_client_timestamp(request)
        resume_time = client_ts or timezone.now()
        # Clamp resume_time to pause_time to prevent negative pause duration
        # when client_timestamp is before the pause_time (offline queue).
        if resume_time < timer.pause_time:
            resume_time = timer.pause_time
        paused_duration = int((resume_time - timer.pause_time).total_seconds())
        timer.total_paused_seconds += max(0, paused_duration)
        timer.pause_time = None
        timer.is_paused = False
        timer.save()

    return JsonResponse(
        {"status": "resumed", "total_paused_seconds": timer.total_paused_seconds}
    )


def _parse_stop_request(request, user):
    """Parse and validate stop_timer request body.

    Returns a dict with keys:
      - notes (str, always, max NOTES_MAX_LENGTH)
      - date (date or None, only if can_edit_time_entries)
      - start_time (time or None, only if can_edit_time_entries)
      - end_time (time or None, only if can_edit_time_entries)
      - pause_duration (float hours or None, only if can_edit_time_entries)
      - error (str or None)
      - field (str or None, set when error is set)
    """
    body = {}
    if request.content_type == "application/json":
        try:
            body = json.loads(request.body) if request.body else {}
        except (ValueError, AttributeError):
            return {"error": "Invalid JSON body", "field": None, "notes": "",
                    "date": None, "start_time": None, "end_time": None,
                    "pause_duration": None}
    else:
        # Form-encoded fallback (z.B. für Tests / externe Clients)
        body = {k: request.POST.getlist(k) if len(request.POST.getlist(k)) > 1 else v
                for k, v in request.POST.items()} if request.POST else {}

    notes_raw = body.get("notes") or ""
    if not isinstance(notes_raw, str):
        notes_raw = str(notes_raw)
    notes = notes_raw[:NOTES_MAX_LENGTH]

    result = {
        "error": None,
        "field": None,
        "notes": notes,
        "date": None,
        "start_time": None,
        "end_time": None,
        "pause_duration": None,
    }

    if not can_edit_time_entries(user):
        return result

    def _err(field, msg):
        result["error"] = msg
        result["field"] = field

    raw_date = body.get("date")
    if raw_date:
        try:
            result["date"] = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            _err("date", f"Invalid date format: {raw_date}")
            return result

    raw_start = body.get("start_time")
    if raw_start:
        try:
            result["start_time"] = datetime.strptime(str(raw_start), "%H:%M").time()
        except (ValueError, TypeError):
            _err("start_time", f"Invalid start_time format: {raw_start}")
            return result

    raw_end = body.get("end_time")
    if raw_end:
        try:
            result["end_time"] = datetime.strptime(str(raw_end), "%H:%M").time()
        except (ValueError, TypeError):
            _err("end_time", f"Invalid end_time format: {raw_end}")
            return result

    raw_pause = body.get("pause_duration")
    if raw_pause not in (None, ""):
        try:
            pause_val = float(raw_pause)
            if pause_val < 0:
                _err("pause_duration", "Break must be ≥ 0")
                return result
            result["pause_duration"] = pause_val
        except (ValueError, TypeError):
            _err("pause_duration", f"Invalid pause_duration: {raw_pause}")
            return result

    # No end > start check: end < start on the same day is interpreted
    # as a day-rollover (e.g. night shift 22:00 → 06:00), matching the
    # behaviour of TimeEntry.calculate_hours().

    return result


@login_required
@require_http_methods(["POST"])
def stop_timer(request, profile_id):
    """Stop timer and create TimeEntry.

    Accepts optional client_timestamp so queued offline stops
    record the correct end time and duration. Accepts optional
    notes (always) and optional override fields for date /
    start_time / end_time / pause_duration (only honored if
    can_edit_time_entries(user) is True; ignored otherwise for
    security).

    DateTimeFields are converted to local project timezone via
    timezone.localtime() before date()/time() extraction.
    When the timer is paused, stop ends at pause_time (not stop_time).
    Uses select_for_update + atomic for create+delete safety.
    Response uses saved TimeEntry.hours_worked.
    """
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)

    with transaction.atomic():
        timer = ActiveTimer.objects.select_for_update().filter(
            profile=profile, user=request.user
        ).first()
        if not timer:
            return JsonResponse({"error": "No active timer found"}, status=404)

        parsed = _parse_stop_request(request, request.user)
        if parsed["error"]:
            return JsonResponse(
                {"error": parsed["error"], "field": parsed["field"]}, status=400
            )

        client_ts = _parse_client_timestamp(request)
        stop_time = client_ts or timezone.now()

        # Clamp stop_time to start_time to prevent negative durations
        # when client_timestamp is before the timer started (offline queue).
        if stop_time < timer.start_time:
            stop_time = timer.start_time

        # Convert DateTimeFields to local project timezone before
        # extracting date()/time() components.
        local_start = timezone.localtime(timer.start_time)
        local_stop = timezone.localtime(stop_time)

        # If timer is paused, the effective stop is at pause_time, not now.
        # Clamp pause_time against start_time to prevent overnight entries
        # when pause_time was manipulated to be before start_time.
        if timer.is_paused and timer.pause_time:
            effective_stop = timezone.localtime(
                max(timer.pause_time, timer.start_time)
            )
        else:
            effective_stop = local_stop

        entry_date = parsed["date"] or local_start.date()
        start_dt = parsed["start_time"] or local_start.time()
        end_dt = parsed["end_time"] or effective_stop.time()
        if parsed["pause_duration"] is not None:
            pause_seconds = parsed["pause_duration"] * 3600
        else:
            pause_seconds = timer.total_paused_seconds

        time_entry = TimeEntry.objects.create(
            profile=profile,
            date=entry_date,
            start_time=start_dt,
            end_time=end_dt,
            pause_duration=round(pause_seconds / 3600, 2),
            notes=parsed["notes"],
        )

        timer.delete()

    return JsonResponse(
        {
            "status": "stopped",
            "hours_worked": float(time_entry.hours_worked),
            "entry_id": time_entry.id,
            "date": str(entry_date),
            "notes_saved": bool(parsed["notes"]),
            "message": f"Time entry created: {float(time_entry.hours_worked)} hours",
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
        reference_time = timer.pause_time or now
        elapsed_seconds = (
            reference_time - timer.start_time
        ).total_seconds() - timer.total_paused_seconds
    else:
        elapsed_seconds = (
            now - timer.start_time
        ).total_seconds() - timer.total_paused_seconds

    elapsed_seconds = max(0, elapsed_seconds)

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
