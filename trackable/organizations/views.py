from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from trackable.organizations.models import Organization, OrganizationMembership
from trackable.organizations.forms import (
    OrganizationForm,
    EmployeeCreateForm,
    HolidayForm,
    OrganizationBrandingForm,
)
from trackable.organizations.decorators import org_manager_required
from trackable.organizations.helpers import (
    can_edit_time_entries,
    can_modify_entry,
    can_create_calendar_entry,
    can_manage_profile_time_entries,
    can_move_entry,
)
from trackable.profiles.models import Profile
from trackable.core.models import Holiday
from trackable.accounts.models import User
from trackable.timetracking.models import (
    ENTRY_TYPE_PLANNED,
    TimeEntry,
    ActiveTimer,
)
import json
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone as tz
import calendar

from trackable.core.utils import hours_and_minutes_to_decimal


@login_required
def org_dashboard(request):
    membership = getattr(request.user, "organization_membership", None)
    if not membership:
        return redirect("org_create")

    organization = membership.organization
    if not membership.is_manager:
        return render(
            request,
            "organizations/employee_dashboard.html",
            {"organization": organization, "membership": membership},
        )

    memberships = organization.memberships.select_related("user").all()
    employee_memberships = [m for m in memberships if m.role == "employee"]
    manager_memberships = [m for m in memberships if m.role == "manager"]

    # Load ActiveTimers for all employee profiles
    employee_user_ids = [m.user_id for m in employee_memberships]
    active_timers = ActiveTimer.objects.filter(
        user_id__in=employee_user_ids,
        profile__user_id__in=employee_user_ids,
    ).select_related("profile", "user")

    # Build per-user lookup
    timers_by_user = {}
    for at in active_timers:
        timers_by_user.setdefault(at.user_id, []).append(at)

    # Attach timer attributes to each employee membership
    for m in employee_memberships:
        timers = timers_by_user.get(m.user_id, [])
        timers.sort(key=lambda t: t.created_at, reverse=True)
        m.active_timers = timers
        m.has_running_timer = any(t for t in timers if not t.is_paused)
        m.has_paused_timer = any(t for t in timers if t.is_paused)
        if m.has_running_timer:
            m.timer_status = "running"
        elif m.has_paused_timer:
            m.timer_status = "paused"
        else:
            m.timer_status = None
        m.timer_profile_titles = ", ".join(t.profile.title for t in timers)

    return render(
        request,
        "organizations/dashboard.html",
        {
            "organization": organization,
            "employee_memberships": employee_memberships,
            "manager_memberships": manager_memberships,
            "total_employees": len(employee_memberships),
        },
    )


@login_required
def org_create(request):
    if hasattr(request.user, "organization_membership"):
        messages.info(request, _("You are already part of an organization."))
        return redirect("org_dashboard")

    if request.method == "POST":
        form = OrganizationForm(request.POST)
        if form.is_valid():
            organization = form.save(commit=False)
            organization.created_by = request.user
            organization.save()
            OrganizationMembership.objects.create(
                organization=organization,
                user=request.user,
                role="manager",
            )
            messages.success(
                request,
                _('Organization "%(name)s" created successfully!')
                % {"name": organization.name},
            )
            return redirect("org_dashboard")
    else:
        form = OrganizationForm()

    return render(request, "organizations/create.html", {"form": form})


@login_required
@org_manager_required
def toggle_time_tracking_mode(request):
    membership = request.user.organization_membership
    organization = membership.organization
    if organization.time_tracking_mode == "classic":
        organization.time_tracking_mode = "restricted"
        status = _("restricted")
    else:
        organization.time_tracking_mode = "classic"
        status = _("classic")
    organization.save()
    messages.success(
        request,
        _("Time tracking mode set to %(mode)s.") % {"mode": status},
    )
    return redirect("org_dashboard")


@login_required
@org_manager_required
def toggle_holidays(request):
    organization = request.user.organization_membership.organization
    organization.holidays_enabled = not organization.holidays_enabled
    organization.save()
    status = _("enabled") if organization.holidays_enabled else _("disabled")
    messages.success(
        request,
        _("Holidays %(status)s.") % {"status": status},
    )
    return redirect("org_dashboard")


@login_required
@org_manager_required
def employee_create(request):
    membership = request.user.organization_membership
    organization = membership.organization

    if request.method == "POST":
        form = EmployeeCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            OrganizationMembership.objects.create(
                organization=organization,
                user=user,
                role="employee",
            )
            # Automatisch ein Standard-Profil für den Mitarbeiter anlegen
            from trackable.profiles.models import Profile
            Profile.objects.create(
                user=user,
                title=_("Employee at %(org)s") % {"org": organization.name},
                position=_("Employee"),
                weekly_hours=form.cleaned_data["weekly_hours"],
                hourly_rate=0,
                contract_start_date=form.cleaned_data.get("contract_start_date"),
                contract_end_date=form.cleaned_data.get("contract_end_date"),
            )
            messages.success(
                request,
                _('Employee "%(name)s" created successfully!')
                % {"name": user.get_full_name() or user.username},
            )
            return redirect("org_dashboard")
    else:
        form = EmployeeCreateForm()

    return render(
        request,
        "organizations/employee_create.html",
        {"form": form, "organization": organization},
    )


@login_required
@org_manager_required
def employee_detail(request, user_id):
    membership = request.user.organization_membership
    organization = membership.organization

    employee_membership = get_object_or_404(
        OrganizationMembership,
        organization=organization,
        user_id=user_id,
    )
    employee = employee_membership.user

    profiles = employee.profiles.all()

    # Load ActiveTimers for this employee's profiles
    active_timers = ActiveTimer.objects.filter(
        user=employee,
        profile__user=employee,
    ).select_related("profile", "user")
    timers_by_profile = {at.profile_id: at for at in active_timers}

    current_date = datetime.now().date()
    profile_data = []
    for profile in profiles:
        entry_months = set(
            profile.time_entries.values_list("date__year", "date__month").distinct()
        )
        entry_months.add((current_date.year, current_date.month))

        months = []
        cumulative_balance = 0
        for year, month in sorted(entry_months, reverse=True):
            hours = profile.get_monthly_hours(year, month)
            target = profile.get_target_hours(year, month)
            balance = profile.get_balance(year, month)
            cumulative_balance += balance
            months.append(
                {
                    "year": year,
                    "month": month,
                    "month_name": datetime(year, month, 1).strftime("%B %Y"),
                    "hours": hours,
                    "target_hours": target,
                    "balance": balance,
                    "cumulative_balance": cumulative_balance,
                    "earnings": profile.get_monthly_earnings(year, month),
                }
            )

        profile_data.append({
            "profile": profile,
            "months": months,
            "active_timer": timers_by_profile.get(profile.id),
        })

    return render(
        request,
        "organizations/employee_detail.html",
        {
            "organization": organization,
            "employee": employee,
            "employee_membership": employee_membership,
            "profile_data": profile_data,
        },
    )


@login_required
@login_required
@org_manager_required
@require_http_methods(["POST"])
def set_target_hours(request, user_id, profile_id):
    """Set weekly_target_hours for an employee's profile (manager only)."""
    membership = request.user.organization_membership
    organization = membership.organization

    employee_membership = get_object_or_404(
        OrganizationMembership,
        organization=organization,
        user_id=user_id,
    )
    employee = employee_membership.user
    profile = get_object_or_404(Profile, pk=profile_id, user=employee)

    hours_str = request.POST.get("weekly_target_hours_hours", "").strip()
    minutes_str = request.POST.get("weekly_target_hours_minutes", "").strip()

    if hours_str == "" and minutes_str == "":
        profile.weekly_target_hours = None
    else:
        try:
            hours = int(hours_str) if hours_str != "" else 0
            minutes = int(minutes_str) if minutes_str != "" else 0
            target_hours = hours_and_minutes_to_decimal(hours, minutes)
            if target_hours > Decimal("99.9999"):
                raise ValueError("Target hours too large")
            profile.weekly_target_hours = target_hours
        except (ValueError, TypeError):
            messages.error(request, _("Invalid value for target hours."))
            return redirect("employee_profile_detail", user_id=user_id, profile_id=profile_id)

    profile.save()
    messages.success(request, _("Weekly target hours updated."))
    return redirect("employee_profile_detail", user_id=user_id, profile_id=profile_id)


@login_required
@org_manager_required
@require_http_methods(["POST"])
def set_contract_dates(request, user_id, profile_id):
    """Set contract_start_date and contract_end_date for a profile."""
    membership = request.user.organization_membership
    organization = membership.organization

    employee_membership = get_object_or_404(
        OrganizationMembership,
        organization=organization,
        user_id=user_id,
    )
    employee = employee_membership.user
    profile = get_object_or_404(Profile, pk=profile_id, user=employee)

    from datetime import date

    start_str = request.POST.get("contract_start_date", "").strip()
    end_str = request.POST.get("contract_end_date", "").strip()

    if start_str:
        try:
            profile.contract_start_date = date.fromisoformat(start_str)
        except (ValueError, TypeError):
            messages.error(request, _("Invalid date format for contract start date."))
            return redirect("employee_profile_detail", user_id=user_id, profile_id=profile_id)
    else:
        profile.contract_start_date = None

    if end_str:
        try:
            profile.contract_end_date = date.fromisoformat(end_str)
        except (ValueError, TypeError):
            messages.error(request, _("Invalid date format for contract end date."))
            return redirect("employee_profile_detail", user_id=user_id, profile_id=profile_id)
    else:
        profile.contract_end_date = None

    # Validate: end date must be after start date
    if (profile.contract_start_date and profile.contract_end_date
            and profile.contract_end_date < profile.contract_start_date):
        messages.error(request, _("Contract end date must be after start date."))
        return redirect("employee_profile_detail", user_id=user_id, profile_id=profile_id)

    profile.save()
    messages.success(request, _("Contract dates updated."))
    return redirect("employee_profile_detail", user_id=user_id, profile_id=profile_id)


@login_required
@org_manager_required
def employee_profile_detail(request, user_id, profile_id):
    membership = request.user.organization_membership
    organization = membership.organization

    employee_membership = get_object_or_404(
        OrganizationMembership,
        organization=organization,
        user_id=user_id,
    )
    employee = employee_membership.user

    profile = get_object_or_404(Profile, pk=profile_id, user=employee)

    import calendar
    from django.utils import timezone

    year = int(request.GET.get("year", timezone.now().year))
    month = int(request.GET.get("month", timezone.now().month))

    time_entries = list(profile.get_monthly_entries(year, month).order_by("date"))
    last_day = calendar.monthrange(year, month)[1]
    from trackable.timetracking.models import VacationEntry

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

    entry_months = set(
        profile.time_entries.values_list("date__year", "date__month").distinct()
    )
    entry_months.add((timezone.now().year, timezone.now().month))
    available_months = sorted(entry_months, reverse=True)

    show_actions = can_manage_profile_time_entries(request.user, profile)

    return render(
        request,
        "organizations/employee_profile_detail.html",
        {
            "organization": organization,
            "employee": employee,
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
            "available_months": available_months,
            "show_actions": show_actions,
        },
    )


@login_required
def org_weekly_calendar(request):
    membership = getattr(request.user, "organization_membership", None)
    if not membership:
        return redirect("org_create")

    organization = membership.organization
    is_manager = membership.is_manager

    # ISO-Kalenderwoche aus URL
    today = tz.now().date()
    iso = today.isocalendar()
    year = int(request.GET.get("year", iso[0]))
    week = int(request.GET.get("week", iso[1]))

    # Wochen-Montag & -Sonntag
    try:
        monday = datetime.fromisocalendar(year, week, 1).date()
    except (ValueError, TypeError):
        monday = today - timedelta(days=today.weekday())
        year, week, _ = monday.isocalendar()

    sunday = monday + timedelta(days=6)
    week_dates = [monday + timedelta(days=i) for i in range(7)]

    # Alle Mitglieder holen
    memberships = organization.memberships.select_related("user").all()

    week_data = []
    for m in memberships:
        user = m.user
        day_cells = [{"entries": [], "total": 0.0} for _ in range(7)]

        profiles = user.profiles.all()
        for profile in profiles:
            day_entries = profile.time_entries.filter(
                date__gte=monday, date__lte=sunday
            ).order_by("date", "start_time")

            for entry in day_entries:
                day_idx = entry.date.weekday()  # 0=Mon … 6=Sun
                day_cells[day_idx]["entries"].append({
                    "entry": entry,
                    "profile_title": profile.title,
                })
                day_cells[day_idx]["total"] += float(entry.hours_worked)

        total_weekly = sum(cell["total"] for cell in day_cells)

        week_data.append({
            "membership": m,
            "user": user,
            "day_cells": day_cells,
            "total_weekly": round(total_weekly, 2),
        })

    # Vorherige / Nächste Woche
    prev_monday = monday - timedelta(days=7)
    next_monday = monday + timedelta(days=7)
    prev_iso = prev_monday.isocalendar()
    next_iso = next_monday.isocalendar()
    today_iso = today.isocalendar()

    # ── Time slots (from org calendar settings) ──
    interval = organization.cal_time_interval or 60
    grid_start = organization.cal_start_time or tz.datetime.strptime("08:00", "%H:%M").time()
    grid_end = organization.cal_end_time or tz.datetime.strptime("20:00", "%H:%M").time()

    time_slots = []
    current = tz.datetime.combine(monday, grid_start)
    end_dt = tz.datetime.combine(monday, grid_end)
    while current <= end_dt:
        time_slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=interval)

    grid_start_mins = grid_start.hour * 60 + grid_start.minute
    grid_end_mins = grid_end.hour * 60 + grid_end.minute
    grid_total_mins = grid_end_mins - grid_start_mins

    # ── Employee list for selector ──
    employee_list = []
    for m in memberships:
        profiles = m.user.profiles.all()
        employee_list.append({
            "user_id": m.user.id,
            "name": m.user.get_full_name() or m.user.username,
            "profile_id": profiles[0].id if profiles else None,
            "profile_title": profiles[0].title if profiles else "",
        })

    # ── Grid data (positioned entries) ──
    grid_columns = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    grid_entries = []  # list of {entry_id, profile_title, user_name, day_idx, start_mins, end_mins, duration_mins, notes, date_str}

    for m in memberships:
        user = m.user
        for profile in user.profiles.all():
            day_entries = profile.time_entries.filter(
                date__gte=monday, date__lte=sunday
            ).order_by("date", "start_time")

            for entry in day_entries:
                day_idx = entry.date.weekday()
                start_mins = entry.start_time.hour * 60 + entry.start_time.minute
                end_mins = entry.end_time.hour * 60 + entry.end_time.minute
                duration_mins = end_mins - start_mins
                grid_entries.append({
                    "entry_id": entry.id,
                    "profile_title": profile.title,
                    "user_name": user.get_full_name() or user.username,
                    "user_id": user.id,
                    "profile_id": profile.id,
                    "date_str": entry.date.isoformat(),
                    "day_idx": day_idx,
                    "start_mins": start_mins,
                    "end_mins": end_mins,
                    "duration_mins": max(duration_mins, 15),
                    "start_time_str": entry.start_time.strftime("%H:%M"),
                    "end_time_str": entry.end_time.strftime("%H:%M"),
                    "notes": entry.notes or "",
                    "hours_worked": float(entry.hours_worked),
                })

    PX_PER_HOUR = 64
    px_per_min = PX_PER_HOUR / 60

    return render(
        request,
        "organizations/weekly_calendar.html",
        {
            "organization": organization,
            "is_manager": is_manager,
            "can_edit": can_edit_time_entries(request.user),
            "can_calendar_edit": True,
            "week_data": week_data,
            "year": year,
            "week": week,
            "monday": monday,
            "sunday": sunday,
            "week_dates": week_dates,
            "prev_url": f"?year={prev_iso[0]}&week={prev_iso[1]}",
            "next_url": f"?year={next_iso[0]}&week={next_iso[1]}",
            "today_url": f"?year={today_iso[0]}&week={today_iso[1]}",
            "timer_only": not can_edit_time_entries(request.user),
            # New grid data
            "time_slots": time_slots,
            "grid_start": grid_start.strftime("%H:%M"),
            "grid_end": grid_end.strftime("%H:%M"),
            "grid_start_mins": grid_start_mins,
            "grid_total_mins": grid_total_mins,
            "PIXEL_RATIO": px_per_min,
            "employee_list": employee_list,
            "grid_entries": grid_entries,
            "grid_columns": grid_columns,
        },
    )


@login_required
@require_http_methods(["POST"])
def move_entry(request, entry_id):
    from trackable.timetracking.models import TimeEntry

    entry = get_object_or_404(TimeEntry, pk=entry_id)

    if not can_move_entry(request.user, entry):
        return JsonResponse(
            {"error": _("You do not have permission to modify this entry.")}, status=403
        )

    new_date_str = request.POST.get("new_date")
    new_start_time_str = request.POST.get("new_start_time")

    if not new_date_str:
        return JsonResponse({"error": _("new_date is required.")}, status=400)

    try:
        entry.date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({"error": _("Invalid date format.")}, status=400)

    if new_start_time_str:
        try:
            new_start = datetime.strptime(new_start_time_str, "%H:%M").time()
            # Preserve duration by adjusting end_time
            old_duration = (
                entry.end_time.hour * 60 + entry.end_time.minute
                - (entry.start_time.hour * 60 + entry.start_time.minute)
            )
            if old_duration <= 0:
                old_duration = 60  # default 1h
            new_start_mins = new_start.hour * 60 + new_start.minute
            new_end_mins = new_start_mins + old_duration
            new_end_hour = new_end_mins // 60
            new_end_min = new_end_mins % 60
            entry.start_time = new_start
            entry.end_time = (
                datetime.strptime(f"{new_end_hour:02d}:{new_end_min:02d}", "%H:%M").time()
            )
        except ValueError:
            return JsonResponse({"error": _("Invalid time format.")}, status=400)

    entry.save()
    return JsonResponse({"status": "ok"})


@login_required
@org_manager_required
def employee_remove(request, user_id):
    membership = request.user.organization_membership
    organization = membership.organization

    employee_membership = get_object_or_404(
        OrganizationMembership,
        organization=organization,
        user_id=user_id,
    )
    employee = employee_membership.user

    if request.method == "POST":
        if employee == request.user:
            messages.error(request, _("You cannot remove yourself from the organization."))
            return redirect("employee_detail", user_id=user_id)

        if employee == organization.created_by:
            messages.error(
                request,
                _("You cannot remove the organization owner."),
            )
            return redirect("employee_detail", user_id=user_id)

        if employee_membership.is_manager:
            messages.error(request, _("You cannot remove another manager."))
            return redirect("employee_detail", user_id=user_id)

        employee_name = employee.get_full_name() or employee.username
        employee.delete()
        messages.success(
            request,
            _("%(name)s's account and all associated data have been deleted.")
            % {"name": employee_name},
        )
        return redirect("org_dashboard")

    return render(
        request,
        "organizations/employee_remove.html",
        {"organization": organization, "employee": employee},
    )


@login_required
@org_manager_required
def holiday_list(request):
    membership = request.user.organization_membership
    organization = membership.organization
    from django.utils import timezone

    current_year = timezone.now().year
    year = int(request.GET.get("year", current_year))
    holidays = organization.holidays.filter(date__year=year).order_by("date")
    year_range = range(current_year - 1, current_year + 3)
    return render(
        request,
        "organizations/holiday_list.html",
        {
            "organization": organization,
            "holidays": holidays,
            "year": year,
            "year_range": year_range,
        },
    )


@login_required
@org_manager_required
def holiday_create(request):
    membership = request.user.organization_membership
    organization = membership.organization

    if request.method == "POST":
        form = HolidayForm(request.POST)
        if form.is_valid():
            holiday = form.save(commit=False)
            holiday.organization = organization
            holiday.save()
            messages.success(
                request,
                _('Holiday "%(name)s" added successfully!') % {"name": holiday.name},
            )
            return redirect("org_holidays")
    else:
        form = HolidayForm()

    return render(
        request,
        "organizations/holiday_form.html",
        {"form": form, "organization": organization},
    )


@login_required
@org_manager_required
def holiday_delete(request, pk):
    membership = request.user.organization_membership
    organization = membership.organization

    holiday = get_object_or_404(Holiday, pk=pk, organization=organization)
    if request.method == "POST":
        holiday.delete()
        messages.success(request, _("Holiday deleted."))
    return redirect("org_holidays")


@login_required
@org_manager_required
def org_branding(request):
    org = request.user.organization_membership.organization
    if request.method == "POST":
        form = OrganizationBrandingForm(request.POST, request.FILES, instance=org)
        if form.is_valid():
            form.save()
            messages.success(request, _("Branding saved."))
            return redirect("org_branding")
    else:
        form = OrganizationBrandingForm(instance=org)
    return render(request, "organizations/branding.html", {
        "form": form,
        "organization": org,
    })


@login_required
def create_entry(request):
    """Create a time entry.

    - Managers can create entries for any employee in their org.
    - Employees can only create entries for themselves.
    """
    membership = getattr(request.user, "organization_membership", None)
    if not membership:
        return JsonResponse({"error": _("No organization membership.")}, status=403)

    if request.method != "POST":
        return JsonResponse({"error": _("Method not allowed.")}, status=405)

    profile_id = request.POST.get("profile_id")
    date_str = request.POST.get("date")
    start_time_str = request.POST.get("start_time")
    end_time_str = request.POST.get("end_time")
    notes = request.POST.get("notes", "")

    if not all([profile_id, date_str, start_time_str, end_time_str]):
        return JsonResponse({"error": _("Missing required fields.")}, status=400)

    try:
        profile = get_object_or_404(Profile, pk=profile_id)
        emp_membership = profile.user.organization_membership
        if not emp_membership or emp_membership.organization != membership.organization:
            return JsonResponse(
                {"error": _("Profile does not belong to this organization.")}, status=403
            )

        # Employees can only create entries for themselves
        if not membership.is_manager and profile.user != request.user:
            return JsonResponse(
                {"error": _("You can only create entries for yourself.")}, status=403
            )

        # Check calendar creation permission
        if not can_create_calendar_entry(request.user, profile):
            return JsonResponse(
                {"error": _("You do not have permission to create this entry.")}, status=403
            )

        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        start = datetime.strptime(start_time_str, "%H:%M").time()
        end = datetime.strptime(end_time_str, "%H:%M").time()

        entry = TimeEntry.objects.create(
            profile=profile,
            date=date_obj,
            start_time=start,
            end_time=end,
            notes=notes,
            pause_duration=0,
            entry_type=ENTRY_TYPE_PLANNED,
        )
        return JsonResponse({
            "status": "ok",
            "entry": {
                "id": entry.id,
                "date": date_str,
                "start_time": start_time_str,
                "end_time": end_time_str,
                "notes": notes,
            },
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
def update_entry(request, entry_id):
    """Update a time entry's notes and/or times.

    - Managers can update any entry in their org.
    - Employees can only update their own entries.
    """
    entry = get_object_or_404(TimeEntry, pk=entry_id)

    if not can_modify_entry(request.user, entry):
        return JsonResponse(
            {"error": _("You do not have permission to modify this entry.")}, status=403
        )

    if request.method != "POST":
        return JsonResponse({"error": _("Method not allowed.")}, status=405)

    try:
        data = json.loads(request.body) if request.content_type == "application/json" else request.POST
    except (json.JSONDecodeError, AttributeError):
        data = request.POST

    notes = data.get("notes")
    start_time_str = data.get("start_time")
    end_time_str = data.get("end_time")

    if notes is not None:
        entry.notes = notes
    if start_time_str:
        entry.start_time = datetime.strptime(start_time_str, "%H:%M").time()
    if end_time_str:
        entry.end_time = datetime.strptime(end_time_str, "%H:%M").time()

    entry.save()
    return JsonResponse({"status": "ok"})


@login_required
@require_http_methods(["POST"])
def delete_calendar_entry(request, entry_id):
    """Delete a time entry from the weekly calendar.

    - Managers can delete any entry in their org.
    - Employees can only delete their own entries.
    """
    entry = get_object_or_404(TimeEntry, pk=entry_id)

    if not can_modify_entry(request.user, entry):
        return JsonResponse(
            {"error": _("You do not have permission to modify this entry.")}, status=403
        )

    entry.delete()
    return JsonResponse({"status": "ok"})
