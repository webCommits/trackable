from django import forms
from django.utils.translation import gettext_lazy as _
from trackable.timetracking.models import TimeEntry, VacationEntry


class TimeEntryForm(forms.ModelForm):
    class Meta:
        model = TimeEntry
        fields = ["date", "start_time", "end_time", "pause_duration", "notes"]
        labels = {
            "date": _("Date"),
            "start_time": _("Start time"),
            "end_time": _("End time"),
            "pause_duration": _("Break (hours)"),
            "notes": _("Activity / Notes"),
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "pause_duration": forms.NumberInput(attrs={"step": "0.25", "min": "0"}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": _("What did you work on? (optional)")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from datetime import date

        if not self.instance.pk:
            self.fields["date"].initial = date.today()


class VacationEntryForm(forms.ModelForm):
    class Meta:
        model = VacationEntry
        fields = ["start_date", "end_date", "notes"]
        labels = {
            "start_date": _("Start date"),
            "end_date": _("End date"),
            "notes": _("Description (optional)"),
        }
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.TextInput(attrs={"placeholder": _("e.g. Summer vacation")}),
        }
