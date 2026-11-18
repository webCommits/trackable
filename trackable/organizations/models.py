from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from datetime import time as time_obj


class Organization(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="created_organizations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    time_tracking_mode = models.CharField(
        max_length=20,
        default="classic",
        choices=[
            ("classic", "Classic \u2013 Full CRUD access"),
            ("restricted", "Restricted \u2013 Timer only (except managers)"),
        ],
        verbose_name="Time tracking mode",
    )
    holidays_enabled = models.BooleanField(
        default=True,
        verbose_name=_("Holidays enabled"),
        help_text=_("When disabled, holidays are not deducted from vacation workday calculations."),
    )

    # Weekly Calendar Settings
    cal_week_starts_on = models.IntegerField(
        default=1,
        choices=[(0, "Sunday"), (1, "Monday")],
        verbose_name="Calendar week starts on",
    )
    cal_included_days = models.CharField(
        max_length=10,
        default="workdays",
        choices=[("all", "All days"), ("workdays", "Workdays (Mon\u2013Fri)")],
        verbose_name="Calendar included days",
    )
    cal_time_interval = models.IntegerField(
        default=60,
        choices=[(15, "15 min"), (30, "30 min"), (60, "60 min")],
        verbose_name="Calendar time interval",
    )
    cal_start_time = models.TimeField(default=time_obj(8, 0), verbose_name="Calendar start time")
    cal_end_time = models.TimeField(default=time_obj(20, 0), verbose_name="Calendar end time")

    # ── Branding / White-Label ──
    logo = models.ImageField(
        upload_to="org_logos/",
        blank=True, null=True,
        verbose_name=_("Logo (Navbar)"),
        help_text=_("Empfohlen: 180×40 px, PNG oder SVG mit transparentem Hintergrund."),
    )
    favicon = models.ImageField(
        upload_to="org_favicons/",
        blank=True, null=True,
        verbose_name=_("Favicon"),
        help_text=_("Empfohlen: 32×32 px, ICO oder PNG."),
    )
    apple_touch_icon = models.ImageField(
        upload_to="org_favicons/",
        blank=True, null=True,
        verbose_name=_("Apple Touch Icon"),
        help_text=_("Empfohlen: 180×180 px, PNG. Wird auf dem iOS-Homescreen verwendet."),
    )
    primary_color = models.CharField(
        max_length=7,
        default="", blank=True,
        verbose_name=_("Primärfarbe"),
        help_text=_("Hex-Farbe (z. B. #ca9ee6). Überschreibt primäre UI-Akzente (Buttons, Badges)."),
    )
    accent_color = models.CharField(
        max_length=7,
        default="", blank=True,
        verbose_name=_("Akzentfarbe"),
        help_text=_("Hex-Farbe (z. B. #8caaee). Überschreibt sekundäre Akzente (Links, Hover)."),
    )
    custom_css = models.TextField(
        blank=True, default="",
        verbose_name=_("Eigenes CSS"),
        help_text=_("Beliebige CSS-Regeln, nach den Standard-Styles geladen."),
    )

    # ── Monthly reports ──
    monthly_report_email = models.EmailField(
        blank=True, default="",
        verbose_name=_("E-Mail-Adresse für Monatsberichte"),
        help_text=_("Erhält eine Kopie aller Monatsberichte der Mitglieder dieser Organisation."),
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            original_slug = self.slug
            counter = 1
            while Organization.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)



class OrganizationMembership(models.Model):
    ROLE_CHOICES = [
        ("manager", "Manager"),
        ("employee", "Employee"),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="organization_membership",
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="employee")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["role", "joined_at"]

    def __str__(self):
        return f"{self.user} – {self.get_role_display()} @ {self.organization}"

    @property
    def is_manager(self):
        return self.role == "manager"
