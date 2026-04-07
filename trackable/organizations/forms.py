from django import forms
from django.utils.translation import gettext_lazy as _
from trackable.organizations.models import Organization
from trackable.accounts.models import User
from trackable.core.models import Holiday


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ["name"]
        labels = {"name": _("Organization name")}


class EmployeeCreateForm(forms.ModelForm):
    temp_password = forms.CharField(
        widget=forms.PasswordInput,
        label=_("Temporary password"),
    )
    temp_password_confirm = forms.CharField(
        widget=forms.PasswordInput,
        label=_("Confirm temporary password"),
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]
        labels = {
            "username": _("Username"),
            "email": _("E-Mail"),
            "first_name": _("First name"),
            "last_name": _("Last name"),
        }

    def clean(self):
        cleaned_data = super().clean()
        pw = cleaned_data.get("temp_password")
        pw_confirm = cleaned_data.get("temp_password_confirm")
        if pw and pw_confirm and pw != pw_confirm:
            raise forms.ValidationError(_("Passwords do not match."))
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["temp_password"])
        user.email_confirmed = True
        if commit:
            user.save()
        return user


class HolidayForm(forms.ModelForm):
    class Meta:
        model = Holiday
        fields = ["date", "name"]
        labels = {
            "date": _("Date"),
            "name": _("Holiday name"),
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }
