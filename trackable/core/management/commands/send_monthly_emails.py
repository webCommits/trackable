from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
import html2text
import re
from xml.sax.saxutils import escape
from datetime import datetime, date
import io
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
from trackable.core.email import get_effective_connection, get_effective_from_email
from trackable.core.reporting import (
    parse_monthly_report_day,
    report_period,
    report_period_label,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Send monthly report emails to users (and, if configured, a copy to their organization)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            dest="date",
            default=None,
            help="Treat this date (YYYY-MM-DD) as 'today'. Useful for testing/manual re-send.",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            default=False,
            help="Do everything except sending emails; print what would happen.",
        )

    def handle(self, *args, **options):
        try:
            report_day = parse_monthly_report_day(
                getattr(settings, "MONTHLY_REPORT_DAY_RAW", "")
            )
        except ValueError as e:
            raise CommandError(str(e))

        date_option = options.get("date")
        if date_option:
            try:
                today = datetime.strptime(date_option, "%Y-%m-%d").date()
            except ValueError:
                raise CommandError(
                    f"Invalid --date value {date_option!r}, expected YYYY-MM-DD."
                )
        else:
            # Local date in settings.TIME_ZONE, not the container's (UTC) clock.
            today = timezone.localdate()

        dry_run = options.get("dry_run", False)

        period = report_period(today, report_day)
        if period is None:
            self.stdout.write(
                self.style.WARNING(
                    f"{today.isoformat()} is not a report send day. Skipping."
                )
            )
            return

        start, end = period
        label = report_period_label(start, end, report_day)

        users = User.objects.filter(is_active=True)

        from_email = get_effective_from_email()
        # Not opened here on purpose: the SMTP backend opens and closes the
        # connection per message, so one dropped connection can't fail all
        # remaining reports. None means Django's default connection (env).
        connection = None if dry_run else get_effective_connection()

        self._send_reports_for_users(
            users, start, end, label, report_day, dry_run, from_email, connection
        )

    def _send_reports_for_users(
        self, users, start, end, label, report_day, dry_run, from_email, connection
    ):
        for user in users:
            employee_name = self.employee_name(user)
            profiles = list(user.profiles.all())
            multiple_profiles = len(profiles) > 1
            for profile in profiles:
                entries = list(profile.get_entries_between(start, end))

                if not entries:
                    continue

                from trackable.timetracking.models import VacationEntry

                vacation_entries = list(
                    profile.vacation_entries.filter(
                        start_date__lte=end,
                        end_date__gte=start,
                    ).order_by("start_date")
                )
                total_vacation_days = sum(v.workdays for v in vacation_entries)

                total_hours = profile.get_hours_between(start, end)
                total_earnings = profile.get_earnings_between(start, end)

                to, bcc = self.get_recipients(user, profile)

                if not to and not bcc:
                    continue

                if dry_run:
                    self.stdout.write(
                        f"[dry-run] {user.username} ({employee_name}) / {profile.title} | "
                        f"period {label} | entries={len(entries)} | "
                        f"hours={total_hours} | to={to} | bcc={bcc}"
                    )
                    continue

                html_message = render_to_string(
                    "emails/monthly_report_email.html",
                    {
                        "user": user,
                        "profile": profile,
                        "employee_name": employee_name,
                        "month_name": label,
                        "total_hours": total_hours,
                        "total_earnings": total_earnings,
                        "vacation_entries": vacation_entries,
                        "total_vacation_days": total_vacation_days,
                    },
                )

                text_message = html2text.html2text(html_message)

                try:
                    pdf_buffer = self.generate_pdf(
                        profile, employee_name, label, start, end, entries
                    )
                    email = EmailMessage(
                        subject=f"Monatsbericht - {employee_name} - {label}",
                        body=text_message,
                        from_email=from_email,
                        to=to,
                        bcc=bcc,
                        connection=connection,
                    )
                    email.attach(
                        self.pdf_filename(
                            employee_name,
                            profile,
                            report_day,
                            start,
                            end,
                            multiple_profiles,
                        ),
                        pdf_buffer.getvalue(),
                        "application/pdf",
                    )
                    email.send(fail_silently=False)

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Sent monthly report for profile {profile.title} "
                            f"(to={to}, bcc={bcc})"
                        )
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to send email for profile {profile.title}: {str(e)}"
                        )
                    )

    def get_recipients(self, user, profile):
        """Determine (to, bcc) for a profile's monthly report.

        - to: the user's own address, if notifications are enabled.
        - bcc: the organization's monthly report address, if configured and
          different (case-insensitively) from the user's address.
        - If `to` ends up empty but `bcc` is set, send directly to the org
          address instead (so it's not silently dropped as a bcc-only mail).
        """
        to = []
        if user.is_active and user.email_notifications_enabled and user.email:
            to = [user.email]

        bcc = []
        membership = getattr(user, "organization_membership", None)
        org = membership.organization if membership else None
        if org and org.monthly_report_email:
            if not user.email or org.monthly_report_email.lower() != user.email.lower():
                bcc = [org.monthly_report_email]

        if not to and bcc:
            to, bcc = bcc, []

        return to, bcc

    def employee_name(self, user):
        """Human-readable name for a user, falling back to the username."""
        return user.get_full_name().strip() or user.username

    def safe_filename_part(self, value):
        """Sanitize a string for use in a filename.

        Runs of characters outside [\\w.-] (unicode word chars allowed) are
        collapsed to a single underscore, and leading/trailing underscores
        are stripped.
        """
        return re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("_")

    def pdf_filename(self, employee_name, profile, report_day, start, end, multiple_profiles=False):
        safe_name = self.safe_filename_part(employee_name)
        if report_day is None:
            suffix = f"{start.year}_{start.month}"
        else:
            suffix = end.isoformat()

        if multiple_profiles:
            safe_title = self.safe_filename_part(profile.title)
            return f"arbeitszeiten_{safe_name}_{safe_title}_{suffix}.pdf"
        return f"arbeitszeiten_{safe_name}_{suffix}.pdf"

    def generate_pdf(self, profile, employee_name, label, start, end, entries):
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

        elements.append(
            Paragraph(
                f"{escape(employee_name)} - {escape(profile.title)} - {escape(label)}",
                title_style,
            )
        )
        elements.append(Paragraph(escape(f"{profile.position}"), styles["Normal"]))
        elements.append(Spacer(1, 20))

        total_hours = profile.get_hours_between(start, end)

        data = [["Datum", "Start", "Ende", "Pause", "Arbeitsstunden", "Tätigkeit"]]

        for entry in entries:
            date_str = entry.date.strftime("%d.%m.%Y")
            start_str = entry.start_time.strftime("%H:%M")
            end_str = entry.end_time.strftime("%H:%M")
            pause_str = f"{entry.pause_duration}h"
            hours_str = f"{entry.hours_worked:.2f}h"
            notes_str = entry.notes or ""
            data.append([date_str, start_str, end_str, pause_str, hours_str, notes_str])

        data.append(["", "", "", "", "Gesamt:", f"{total_hours:.2f}h"])

        table = Table(
            data, colWidths=[1.3*inch, 0.85*inch, 0.85*inch, 0.85*inch, 1.2*inch, 3.4*inch]
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

        total_earnings = profile.get_earnings_between(start, end)
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
