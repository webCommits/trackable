from django import forms
from django.utils.translation import gettext_lazy as _
from trackable.profiles.models import Profile


class ProfileForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        # Accept German decimal comma (e.g. 4,33 → 4.33)
        data = kwargs.get("data")
        if data:
            data = data.copy()
            for key in data:
                if isinstance(data[key], str):
                    data[key] = data[key].replace(",", ".")
            kwargs["data"] = data
        super().__init__(*args, **kwargs)

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
            "weekly_hours": forms.TextInput(attrs={"placeholder": _("e.g. 40,00")}),
            "hourly_rate": forms.TextInput(attrs={"placeholder": _("e.g. 50,00")}),
            "internal_notes": forms.Textarea(
                attrs={"rows": 4, "placeholder": _("Contract start, department, notes for payroll, …")}
            ),
        }
