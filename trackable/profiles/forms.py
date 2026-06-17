from decimal import Decimal
from django import forms
from django.utils.translation import gettext_lazy as _
from trackable.core.utils import decimal_to_hours_and_minutes, hours_and_minutes_to_decimal
from trackable.profiles.models import Profile


class ProfileForm(forms.ModelForm):
    weekly_hours_hours = forms.IntegerField(
        min_value=0,
        max_value=168,
        required=True,
        label=_("Weekly hours"),
        widget=forms.NumberInput(attrs={"placeholder": _("e.g. 4"), "min": 0, "max": 168}),
    )
    weekly_hours_minutes = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        initial=0,
        label=_("Minutes"),
        widget=forms.NumberInput(attrs={"placeholder": _("e.g. 20"), "min": 0, "max": 59}),
    )

    def __init__(self, *args, **kwargs):
        # Normalize German decimal commas (e.g. 50,00 -> 50.00) whether data is
        # passed positionally or as a keyword argument.
        if args:
            data = args[0]
            if hasattr(data, "copy"):
                data = data.copy()
                for key in list(data.keys()):
                    if isinstance(data[key], str):
                        data[key] = data[key].replace(",", ".")
                args = (data,) + args[1:]
        else:
            data = kwargs.get("data")
            if data:
                data = data.copy()
                for key in list(data.keys()):
                    if isinstance(data[key], str):
                        data[key] = data[key].replace(",", ".")
                kwargs["data"] = data

        instance = kwargs.get("instance")
        if instance and instance.weekly_hours is not None:
            initial = kwargs.setdefault("initial", {})
            hours, minutes = decimal_to_hours_and_minutes(instance.weekly_hours)
            initial.setdefault("weekly_hours_hours", hours)
            initial.setdefault("weekly_hours_minutes", minutes)
        super().__init__(*args, **kwargs)

    class Meta:
        model = Profile
        fields = ["title", "position", "address", "hourly_rate", "internal_notes"]
        labels = {
            "title": _("Job title"),
            "position": _("Position"),
            "address": _("Address (optional)"),
            "hourly_rate": _("Hourly rate (€)"),
            "internal_notes": _("Internal notes (optional)"),
        }
        widgets = {
            "address": forms.Textarea(
                attrs={"rows": 3, "placeholder": _("Street, ZIP, City")}
            ),
            "hourly_rate": forms.TextInput(attrs={"placeholder": _("e.g. 50,00")}),
            "internal_notes": forms.Textarea(
                attrs={"rows": 4, "placeholder": _("Contract start, department, notes for payroll, …")}
            ),
        }



    def clean(self):
        cleaned_data = super().clean()
        hours = cleaned_data.get("weekly_hours_hours")
        minutes = cleaned_data.get("weekly_hours_minutes") or 0

        if hours is not None:
            weekly_hours = hours_and_minutes_to_decimal(hours, minutes)
            if weekly_hours > Decimal("99.9999"):
                self.add_error(
                    "weekly_hours_hours",
                    _("Weekly hours must be at most 99.9999 hours."),
                )
            cleaned_data["weekly_hours"] = weekly_hours

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.weekly_hours = self.cleaned_data["weekly_hours"]
        if commit:
            instance.save()
        return instance
