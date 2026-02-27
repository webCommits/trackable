from django import forms
from trackable.profiles.models import Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["title", "position", "address", "weekly_hours", "hourly_rate"]
        labels = {
            "title": "Jobtitel",
            "position": "Stelle",
            "address": "Adresse (optional)",
            "weekly_hours": "Wochenstunden",
            "hourly_rate": "Stundenlohn (€)",
        }
        widgets = {
            "address": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Straße, PLZ, Stadt"}
            ),
            "weekly_hours": forms.NumberInput(attrs={"step": "0.5", "min": "0"}),
            "hourly_rate": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }
