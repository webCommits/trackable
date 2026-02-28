from django import forms
from django.utils.translation import gettext_lazy as _
from trackable.profiles.models import Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["title", "position", "address", "weekly_hours", "hourly_rate", "internal_notes"]
        labels = {
            "title": _("Job title"),
            "position": _("Position"),
            "address": _("Address (optional)"),
            "weekly_hours": _("Weekly hours"),
            "hourly_rate": _("Hourly rate (€)"),
            "internal_notes": _("Internal notes (optional)"),
        }
        widgets = {
            "address": forms.Textarea(
                attrs={"rows": 3, "placeholder": _("Street, ZIP, City")}
            ),
            "weekly_hours": forms.NumberInput(attrs={"step": "0.5", "min": "0"}),
            "hourly_rate": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "internal_notes": forms.Textarea(
                attrs={"rows": 4, "placeholder": _("Contract start, department, notes for payroll, …")}
            ),
        }
