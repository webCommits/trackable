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
from trackable.timetracking.forms import TimeEntryForm, VacationEntryForm
from trackable.timetracking.models import TimeEntry, VacationEntry
from trackable.profiles.models import Profile


@login_required
def home(request):
    profiles = request.user.profiles.all()
    if profiles.count() == 0:
        return redirect("profile_create")
    return render(request, "timetracking/home.html", {"profiles": profiles})


@login_required
def add_entry(request, profile_id):
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)
    if request.method == "POST":
        form = TimeEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.profile = profile
            entry.save()
            messages.success(request, _("Time entry for %(date)s was saved successfully!") % {"date": entry.date})
            return redirect("profile_detail", pk=profile.pk)
    else:
        form = TimeEntryForm()
    return render(request, "timetracking/add_entry.html", {"form": form, "profile": profile})


@login_required
def edit_entry(request, pk):
    entry = get_object_or_404(TimeEntry, pk=pk, profile__user=request.user)
    profile = entry.profile
    if request.method == "POST":
        form = TimeEntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            messages.success(request, _("Time entry was updated successfully!"))
            return redirect("monthly_table", profile_id=profile.pk, year=entry.date.year, month=entry.date.month)
    else:
        form = TimeEntryForm(instance=entry)
    return render(request, "timetracking/add_entry.html", {"form": form, "profile": profile, "edit": True})


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
    return render(request, "timetracking/monthly_table.html", {
        "profile": profile,
        "time_entries": time_entries,
        "vacation_entries": vacation_entries,
        "year": year,
        "month": month,
        "month_name": month_name,
        "total_hours": total_hours,
        "total_earnings": total_earnings,
        "total_vacation_days": total_vacation_days,
    })


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
    return render(request, "timetracking/add_vacation.html", {"form": form, "profile": profile})


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
        profile.vacation_entries.filter(start_date__year=year) |
        profile.vacation_entries.filter(end_date__year=year)
    ).distinct().order_by("start_date")
    total_days = sum(v.workdays for v in vacations)
    year_range = range(current_year - 2, current_year + 2)
    return render(request, "timetracking/vacation_overview.html", {
        "profile": profile,
        "vacations": vacations,
        "year": year,
        "year_range": year_range,
        "total_days": total_days,
    })


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
        "CustomTitle", parent=styles["Heading1"],
        fontSize=18, textColor=colors.HexColor("#8839ef"), spaceAfter=20,
    )

    elements.append(Paragraph(f"{profile.title} - {month_name}", title_style))
    elements.append(Paragraph(f"{profile.position}", styles["Normal"]))
    if profile.address:
        elements.append(Paragraph(profile.address, styles["Normal"]))
    elements.append(Spacer(1, 20))

    # Time entries table
    data = [[_g("Date"), _g("Start"), _g("End"), _g("Break"), _g("Hours"), _g("Activity")]]
    for entry in time_entries:
        data.append([
            entry.date.strftime("%d.%m.%Y"),
            entry.start_time.strftime("%H:%M"),
            entry.end_time.strftime("%H:%M"),
            f"{entry.pause_duration}h",
            f"{entry.hours_worked:.2f}h",
            entry.notes or "",
        ])
    data.append(["", "", "", "", _g("Total:"), f"{total_hours:.2f}h"])

    col_widths = [1.3*inch, 0.85*inch, 0.85*inch, 0.85*inch, 1.2*inch, 3.4*inch]
    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#8839ef")),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  11),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  10),
        ("BACKGROUND",    (0, 1), (-1, -2), colors.white),
        ("GRID",          (0, 0), (-1, -2), 0.5, colors.HexColor("#dce0e8")),
        ("FONTNAME",      (0, 0), (-1, -2), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -2), 9),
        ("ALIGN",         (0, 0), (-1, -2), "LEFT"),
        ("BACKGROUND",    (0, -1), (-1, -1), colors.HexColor("#f8fafc")),
        ("FONTNAME",      (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, -1), (-1, -1), 11),
        ("ALIGN",         (4, -1), (-1, -1), "RIGHT"),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 20))

    earnings_style = ParagraphStyle(
        "Earnings", parent=styles["Heading2"],
        fontSize=15, textColor=colors.HexColor("#40a02b"),
    )
    elements.append(Paragraph(f"{_g('Total earnings')}: €{total_earnings:.2f}", earnings_style))

    # Vacation section
    if vacation_entries:
        elements.append(Spacer(1, 24))
        elements.append(Paragraph(_g("Vacation / Absences"), ParagraphStyle(
            "VacTitle", parent=styles["Heading2"],
            fontSize=13, textColor=colors.HexColor("#179299"), spaceAfter=8,
        )))
        vac_data = [[_g("Period"), _g("Working days"), _g("Weeks"), _g("Description")]]
        for v in vacation_entries:
            vac_data.append([
                f"{v.start_date.strftime('%d.%m.%Y')} – {v.end_date.strftime('%d.%m.%Y')}",
                str(v.workdays),
                str(v.weeks),
                v.notes or "",
            ])
        vac_data.append([_g("Total"), str(total_vacation_days), "", ""])
        vac_table = Table(vac_data, colWidths=[2.4*inch, 1.1*inch, 1*inch, 4.1*inch])
        vac_table.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0),  colors.HexColor("#179299")),
            ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, 0),  10),
            ("BACKGROUND",   (0, 1), (-1, -2), colors.white),
            ("GRID",         (0, 0), (-1, -2), 0.5, colors.HexColor("#dce0e8")),
            ("FONTSIZE",     (0, 1), (-1, -1), 9),
            ("BACKGROUND",   (0, -1), (-1, -1), colors.HexColor("#f8fafc")),
            ("FONTNAME",     (0, -1), (-1, -1), "Helvetica-Bold"),
        ]))
        elements.append(vac_table)

    doc.build(elements)
    buffer.seek(0)
    response.write(buffer.getvalue())
    return response


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
    writer.writerow([
        _g("Date"), _g("Start"), _g("End"), _g("Break") + " (h)",
        _g("Hours"), _g("Activity"),
    ])
    for entry in time_entries:
        writer.writerow([
            entry.date.strftime("%d.%m.%Y"),
            entry.start_time.strftime("%H:%M"),
            entry.end_time.strftime("%H:%M"),
            str(entry.pause_duration).replace(".", ","),
            str(round(entry.hours_worked, 2)).replace(".", ","),
            entry.notes or "",
        ])
    return response
