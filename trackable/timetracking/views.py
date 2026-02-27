from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
from datetime import datetime, timedelta
import io
from trackable.timetracking.forms import TimeEntryForm
from trackable.timetracking.models import TimeEntry
from trackable.profiles.models import Profile


@login_required
def home(request):
    if not request.user.is_authenticated:
        return redirect("login")

    profiles = request.user.profiles.all()

    if profiles.count() == 0:
        return redirect("profile_create")

    return render(
        request,
        "timetracking/home.html",
        {
            "profiles": profiles,
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
                request, f"Zeiteintrag für {entry.date} wurde erfolgreich hinzugefügt!"
            )
            return redirect("profile_detail", pk=profile.pk)
    else:
        form = TimeEntryForm()

    return render(
        request,
        "timetracking/add_entry.html",
        {
            "form": form,
            "profile": profile,
        },
    )


@login_required
def monthly_table(request, profile_id, year, month):
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)
    entries = profile.get_monthly_entries(year, month).order_by("date")

    total_hours = profile.get_monthly_hours(year, month)
    total_earnings = profile.get_monthly_earnings(year, month)

    month_name = datetime(year, month, 1).strftime("%B %Y")

    return render(
        request,
        "timetracking/monthly_table.html",
        {
            "profile": profile,
            "entries": entries,
            "year": year,
            "month": month,
            "month_name": month_name,
            "total_hours": total_hours,
            "total_earnings": total_earnings,
        },
    )


@login_required
def export_pdf(request, profile_id, year, month):
    profile = get_object_or_404(Profile, pk=profile_id, user=request.user)
    entries = profile.get_monthly_entries(year, month).order_by("date")

    total_hours = profile.get_monthly_hours(year, month)
    total_earnings = profile.get_monthly_earnings(year, month)

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
        textColor=colors.HexColor("#6366f1"),
        spaceAfter=20,
    )

    elements.append(Paragraph(f"{profile.title} - {month_name}", title_style))
    elements.append(Paragraph(f"{profile.position}", styles["Normal"]))
    elements.append(Spacer(1, 20))

    data = [["Datum", "Start", "Ende", "Pause", "Arbeitsstunden"]]

    for entry in entries:
        date_str = entry.date.strftime("%d.%m.%Y")
        start_str = entry.start_time.strftime("%H:%M")
        end_str = entry.end_time.strftime("%H:%M")
        pause_str = f"{entry.pause_duration}h"
        hours_str = f"{entry.hours_worked:.2f}h"
        data.append([date_str, start_str, end_str, pause_str, hours_str])

    data.append(["", "", "", "Gesamt:", f"{total_hours:.2f}h"])

    table = Table(
        data, colWidths=[1.5 * inch, 1 * inch, 1 * inch, 1 * inch, 1.5 * inch]
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6366f1")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 12),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -2), colors.white),
                ("GRID", (0, 0), (-1, -2), 1, colors.grey),
                ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -2), 10),
                ("ALIGN", (0, 0), (-1, -2), "LEFT"),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f8fafc")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, -1), (-1, -1), 12),
                ("ALIGN", (0, -1), (-1, -1), "RIGHT"),
            ]
        )
    )

    elements.append(table)
    elements.append(Spacer(1, 30))

    earnings_style = ParagraphStyle(
        "Earnings",
        parent=styles["Heading2"],
        fontSize=16,
        textColor=colors.HexColor("#10b981"),
    )
    elements.append(
        Paragraph(f"Gesamtverdienst: €{total_earnings:.2f}", earnings_style)
    )

    doc.build(elements)
    buffer.seek(0)
    response.write(buffer.getvalue())

    return response
