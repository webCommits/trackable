from django import forms
from trackable.timetracking.models import TimeEntry


class TimeEntryForm(forms.ModelForm):
    class Meta:
        model = TimeEntry
        fields = ["date", "start_time", "end_time", "pause_duration"]
        labels = {
            "date": "Datum",
            "start_time": "Startzeit",
            "end_time": "Endzeit",
            "pause_duration": "Pause (Stunden)",
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "pause_duration": forms.NumberInput(attrs={"step": "0.25", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.utils import timezone
        from datetime import date

        if not self.instance.pk:
            self.fields["date"].initial = date.today()
