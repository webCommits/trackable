from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext as _g
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
from datetime import datetime, timedelta
import calendar
import csv
import io
from datetime import time as time_obj
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from trackable.timetracking.forms import TimeEntryForm, VacationEntryForm
from trackable.timetracking.models import TimeEntry, VacationEntry, ActiveTimer
from trackable.profiles.models import Profile


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
    if profiles.count() == 0:
        return redirect("profile_create")
    return render(
        request,
        "timetracking/home.html",
        {
            "profiles": profiles,
            "active_timers": active_timers,
            "has_org": has_org,
        },
    )


@login_required
def add_entry(request, profile_id):
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)
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
            return redirect("profile_detail", pk=profile.pk)
    else:
        form = TimeEntryForm()
    return render(
        request, "timetracking/add_entry.html", {"form": form, "profile": profile}
    )


@login_required
def edit_entry(request, pk):
    entry = get_object_or_404(TimeEntry, pk=pk, profile__user=request.user)
    profile = entry.profile
    if request.method == "POST":
        form = TimeEntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            messages.success(request, _("Time entry was updated successfully!"))
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
    entry = get_object_or_404(TimeEntry, pk=pk, profile__user=request.user)
    year, month = entry.date.year, entry.date.month
    profile_id = entry.profile_id
    if request.method == "POST":
        entry.delete()
        messages.success(request, _("Time entry was deleted."))
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
    total_vacation_days = sum(v.workdays for v in vacation_entries)
    month_name = datetime(year, month, 1).strftime("%B %Y")
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
            "total_vacation_days": total_vacation_days,
        },
    )


# ── Vacation ──────────────────────────────────────────────────────────────────


@login_required
def add_vacation(request, profile_id):
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)
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
    profile_id = vacation.profile_id
    if request.method == "POST":
        vacation.delete()
        messages.success(request, _("Vacation entry was deleted."))
    return redirect("vacation_overview", profile_id=profile_id)


@login_required
def vacation_overview(request, profile_id):
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)
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
    total_vacation_days = sum(v.workdays for v in vacation_entries)
    month_name = datetime(year, month, 1).strftime("%B %Y")

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="arbeitszeiten_{profile.title}_{year}_{month}.pdf"'
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#8839ef"),
        spaceAfter=20,
    )

    elements.append(Paragraph(f"{profile.title} - {month_name}", title_style))
    elements.append(Paragraph(f"{profile.position}", styles["Normal"]))
    if profile.address:
        elements.append(Paragraph(profile.address, styles["Normal"]))
    elements.append(Spacer(1, 20))

    # Time entries table
    data = [
        [_g("Date"), _g("Start"), _g("End"), _g("Break"), _g("Hours"), _g("Activity")]
    ]
    for entry in time_entries:
        data.append(
            [
                entry.date.strftime("%d.%m.%Y"),
                entry.start_time.strftime("%H:%M"),
                entry.end_time.strftime("%H:%M"),
                f"{entry.pause_duration}h",
                f"{entry.hours_worked:.2f}h",
                entry.notes or "",
            ]
        )
    return response


# ── Timer API Endpoints ───────────────────────────────────────────────────────


@login_required
@require_http_methods(["POST"])
def start_timer(request, profile_id):
    """Start a timer for a profile."""
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)

    existing_timer = ActiveTimer.objects.filter(
        profile=profile, user=request.user
    ).first()
    if existing_timer:
        return JsonResponse(
            {"error": "Timer already running for this profile"}, status=400
        )

    timer = ActiveTimer.objects.create(
        profile=profile, user=request.user, start_time=timezone.now(), is_paused=False
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
    """Pause a running timer."""
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)

    timer = ActiveTimer.objects.filter(profile=profile, user=request.user).first()
    if not timer:
        return JsonResponse({"error": "No active timer found"}, status=404)

    if timer.is_paused:
        return JsonResponse({"error": "Timer is already paused"}, status=400)

    timer.pause_time = timezone.now()
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
    """Resume a paused timer."""
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)

    timer = ActiveTimer.objects.filter(profile=profile, user=request.user).first()
    if not timer:
        return JsonResponse({"error": "No active timer found"}, status=404)

    if not timer.is_paused:
        return JsonResponse({"error": "Timer is not paused"}, status=400)

    now = timezone.now()
    paused_duration = int((now - timer.pause_time).total_seconds())
    timer.total_paused_seconds += paused_duration
    timer.pause_time = None
    timer.is_paused = False
    timer.save()

    return JsonResponse(
        {"status": "resumed", "total_paused_seconds": timer.total_paused_seconds}
    )


@login_required
@require_http_methods(["POST"])
def stop_timer(request, profile_id):
    """Stop timer and create TimeEntry."""
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)

    timer = ActiveTimer.objects.filter(profile=profile, user=request.user).first()
    if not timer:
        return JsonResponse({"error": "No active timer found"}, status=404)

    now = timezone.now()
    total_seconds = (
        now - timer.start_time
    ).total_seconds() - timer.total_paused_seconds

    if total_seconds < 0:
        total_seconds = 0

    hours_worked = total_seconds / 3600

    entry_date = timer.start_time.date()
    start_time_obj = timer.start_time.time()
    end_time_obj = now.time()

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
