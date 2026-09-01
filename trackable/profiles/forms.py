from decimal import Decimal, ROUND_HALF_UP
from django import forms
from django.utils.translation import gettext_lazy as _
from trackable.core.utils import decimal_to_hours_and_minutes, hours_and_minutes_to_decimal
from trackable.profiles.models import (
    AVERAGE_WEEKS_PER_MONTH,
    Profile,
    TARGET_HOURS_MONTHLY,
    TARGET_HOURS_PERIOD_CHOICES,
    TARGET_HOURS_WEEKLY,
)


def monthly_to_weekly_equivalent(monthly_hours):
    return (monthly_hours / Decimal(str(AVERAGE_WEEKS_PER_MONTH))).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


class ProfileForm(forms.ModelForm):
    target_hours_period = forms.ChoiceField(
        choices=TARGET_HOURS_PERIOD_CHOICES,
        initial=TARGET_HOURS_WEEKLY,
        required=False,
        label=_("Target hours period"),
    )
    weekly_hours_hours = forms.IntegerField(
        min_value=0,
        max_value=168,
        required=False,
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
    monthly_target_hours_hours = forms.IntegerField(
        min_value=0,
        max_value=999,
        required=False,
        label=_("Monthly hours"),
        widget=forms.NumberInput(attrs={"placeholder": _("e.g. 78"), "min": 0, "max": 999}),
    )
    monthly_target_hours_minutes = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        initial=0,
        label=_("Minutes"),
        widget=forms.NumberInput(attrs={"placeholder": _("e.g. 15"), "min": 0, "max": 59}),
    )
    target_hours_valid_from = forms.DateField(
        required=False,
        input_formats=["%Y-%m"],
        label=_("Valid from"),
        widget=forms.DateInput(attrs={"type": "month"}),
    )

    def __init__(self, *args, **kwargs):
        # Normalize German decimal commas (e.g. 50,00 -> 50.00) whether data is
        # passed positionally or as a keyword argument.
        user = kwargs.pop("user", None)
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
            initial.setdefault("target_hours_period", instance.target_hours_period)
            hours, minutes = decimal_to_hours_and_minutes(instance.weekly_hours)
            initial.setdefault("weekly_hours_hours", hours)
            initial.setdefault("weekly_hours_minutes", minutes)
            if instance.monthly_target_hours is not None:
                monthly_hours, monthly_minutes = decimal_to_hours_and_minutes(
                    instance.monthly_target_hours
                )
                initial.setdefault("monthly_target_hours_hours", monthly_hours)
                initial.setdefault("monthly_target_hours_minutes", monthly_minutes)
        super().__init__(*args, **kwargs)

        # Organization employees may not edit their own contract dates;
        # managers and users without an org membership may.
        if user is not None and self._is_org_employee(user):
            self.fields.pop("contract_start_date", None)
            self.fields.pop("contract_end_date", None)

    @staticmethod
    def _is_org_employee(user):
        membership = getattr(user, "organization_membership", None)
        return membership is not None and not membership.is_manager

    class Meta:
        model = Profile
        fields = [
            "title",
            "position",
            "address",
            "hourly_rate",
            "contract_start_date",
            "contract_end_date",
            "internal_notes",
        ]
        labels = {
            "title": _("Job title"),
            "position": _("Position"),
            "address": _("Address (optional)"),
            "hourly_rate": _("Hourly rate (€)"),
            "contract_start_date": _("Contract start date"),
            "contract_end_date": _("Contract end date"),
            "internal_notes": _("Internal notes (optional)"),
        }
        widgets = {
            "address": forms.Textarea(
                attrs={"rows": 3, "placeholder": _("Street, ZIP, City")}
            ),
            "hourly_rate": forms.TextInput(attrs={"placeholder": _("e.g. 50,00")}),
            "contract_start_date": forms.DateInput(attrs={"type": "date"}),
            "contract_end_date": forms.DateInput(attrs={"type": "date"}),
            "internal_notes": forms.Textarea(
                attrs={"rows": 4, "placeholder": _("Department, notes for payroll, …")}
            ),
        }



    def clean(self):
        cleaned_data = super().clean()
        hours = cleaned_data.get("weekly_hours_hours")
        minutes = cleaned_data.get("weekly_hours_minutes") or 0
        monthly_hours_input = cleaned_data.get("monthly_target_hours_hours")
        monthly_minutes = cleaned_data.get("monthly_target_hours_minutes") or 0
        period = cleaned_data.get("target_hours_period") or TARGET_HOURS_WEEKLY

        if period == TARGET_HOURS_WEEKLY:
            if hours is None:
                self.add_error("weekly_hours_hours", _("Weekly hours are required."))
                return cleaned_data
            weekly_hours = hours_and_minutes_to_decimal(hours, minutes)
            if weekly_hours > Decimal("99.9999"):
                self.add_error(
                    "weekly_hours_hours",
                    _("Weekly hours must be at most 99.9999 hours."),
                )
            cleaned_data["weekly_hours"] = weekly_hours
            cleaned_data["monthly_target_hours"] = None
        elif period == TARGET_HOURS_MONTHLY:
            if monthly_hours_input is None:
                self.add_error(
                    "monthly_target_hours_hours", _("Monthly hours are required.")
                )
                return cleaned_data
            monthly_hours = hours_and_minutes_to_decimal(
                monthly_hours_input, monthly_minutes
            )
            if monthly_hours > Decimal("999.9999"):
                self.add_error(
                    "monthly_target_hours_hours",
                    _("Monthly hours must be at most 999.9999 hours."),
                )
            cleaned_data["monthly_target_hours"] = monthly_hours
            cleaned_data["weekly_hours"] = monthly_to_weekly_equivalent(monthly_hours)

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.weekly_hours = self.cleaned_data["weekly_hours"]
        instance.target_hours_period = self.cleaned_data["target_hours_period"]
        instance.monthly_target_hours = self.cleaned_data["monthly_target_hours"]
        if instance.target_hours_period == TARGET_HOURS_MONTHLY:
            instance.weekly_target_hours = None
        if commit:
            instance.save()
        return instance
