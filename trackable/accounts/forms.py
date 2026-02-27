from django import forms
from trackable.accounts.models import User


class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, label="Passwort")
    password_confirm = forms.CharField(
        widget=forms.PasswordInput, label="Passwort bestätigen"
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]
        labels = {
            "username": "Benutzername",
            "email": "E-Mail",
            "first_name": "Vorname",
            "last_name": "Nachname",
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Die Passwörter stimmen nicht überein.")

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user
