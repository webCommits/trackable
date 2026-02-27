from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import html2text
from datetime import datetime
import calendar
import io
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
from trackable.profiles.models import Profile

User = get_user_model()


class Command(BaseCommand):
    help = "Send monthly report emails to users with email notifications enabled"

    def handle(self, *args, **options):
        today = datetime.now()
        last_day = calendar.monthrange(today.year, today.month)[1]

        if today.day != last_day:
            self.stdout.write(
                self.style.WARNING(
                    f"Today is not the last day of the month ({today.day}/{last_day}). Skipping."
                )
            )
            return

        users = User.objects.filter(email_notifications_enabled=True)

        for user in users:
            for profile in user.profiles.all():
                from trackable.timetracking.models import TimeEntry

                entries = profile.get_monthly_entries(today.year, today.month)

                if not entries:
                    continue

                pdf_buffer = self.generate_pdf(
                    profile, today.year, today.month, entries
                )

                html_message = render_to_string(
                    "emails/monthly_report_email.html",
                    {
                        "user": user,
                        "profile": profile,
                        "month_name": datetime(today.year, today.month, 1).strftime(
                            "%B %Y"
                        ),
                        "total_hours": profile.get_monthly_hours(
                            today.year, today.month
                        ),
                        "total_earnings": profile.get_monthly_earnings(
                            today.year, today.month
                        ),
                    },
                )

                text_message = html2text.html2text(html_message)

                try:
                    send_mail(
                        f"Monatsbericht - {profile.title} - {datetime(today.year, today.month, 1).strftime('%B %Y')}",
                        text_message,
                        settings.DEFAULT_FROM_EMAIL,
                        [user.email],
                        html_message=html_message,
                        fail_silently=False,
                    )

                    pdf_buffer = self.generate_pdf(
                        profile, today.year, today.month, entries
                    )

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Sent monthly report to {user.email} for profile {profile.title}"
                        )
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to send email to {user.email}: {str(e)}"
                        )
                    )

    def generate_pdf(self, profile, year, month, entries):
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

        month_name = datetime(year, month, 1).strftime("%B %Y")
        elements.append(Paragraph(f"{profile.title} - {month_name}", title_style))
        elements.append(Paragraph(f"{profile.position}", styles["Normal"]))
        elements.append(Spacer(1, 20))

        total_hours = profile.get_monthly_hours(year, month)

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

        total_earnings = profile.get_monthly_earnings(year, month)
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
        return buffer
