from django import forms
from django.utils.translation import gettext_lazy as _
from trackable.organizations.models import Organization
from trackable.accounts.models import User
from trackable.core.models import Holiday
from trackable.profiles.models import Profile


class OrganizationBrandingForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = [
            "logo", "favicon", "apple_touch_icon",
            "primary_color", "accent_color", "custom_css",
        ]
        widgets = {
            "primary_color": forms.TextInput(attrs={
                "type": "color",
                "style": "width:60px; height:44px; padding:4px; cursor:pointer;",
            }),
            "accent_color": forms.TextInput(attrs={
                "type": "color",
                "style": "width:60px; height:44px; padding:4px; cursor:pointer;",
            }),
            "custom_css": forms.Textarea(attrs={
                "rows": 10,
                "class": "form-control css-editor",
                "placeholder": _("/* Custom CSS rules */"),
                "style": "font-family:monospace; font-size:.88rem;",
            }),
        }
        help_texts = {
            "logo": _("Empfohlen: 180×40 px, PNG oder SVG. Ersetzt das Logo in der Navigationsleiste."),
            "favicon": _("Empfohlen: 32×32 px, ICO oder PNG."),
            "apple_touch_icon": _("Empfohlen: 180×180 px, PNG. iOS-Homescreen-Symbol."),
            "primary_color": _("Hex-Farbe (#RRGGBB). Überschreibt primäre UI-Akzente (Buttons, Badges)."),
            "accent_color": _("Hex-Farbe (#RRGGBB). Überschreibt sekundäre Akzente (Links, Hover)."),
            "custom_css": _("Beliebige CSS-Regeln (z. B. .btn-primary { background: #xyz; }). Wird nach allen Standard-Styles geladen."),
        }


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
    weekly_hours = forms.DecimalField(
        max_digits=4, decimal_places=2,
        label=_("Weekly hours"),
        initial=40.0,
        help_text=_("Standard working hours per week (e.g. 40)."),
    )
    contract_start_date = forms.DateField(
        label=_("Contract start date"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text=_("Target hours are calculated from this date."),
    )
    contract_end_date = forms.DateField(
        label=_("Contract end date"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text=_("Optional. Leave empty for open-ended contracts."),
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

        start = cleaned_data.get("contract_start_date")
        end = cleaned_data.get("contract_end_date")
        if start and end and end < start:
            raise forms.ValidationError(_("Contract end date must be after start date."))

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["temp_password"])
        user.email_confirmed = True
        if commit:
            user.save()
        return user


class TimeEntryImportForm(forms.Form):
    """First step: upload file + configure parsing options."""

    employee = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label=_("Employee"),
    )
    profile = forms.ModelChoiceField(
        queryset=Profile.objects.none(),
        label=_("Profile"),
        required=True,
    )
    file = forms.FileField(
        label=_("Import file"),
        help_text=_("Accepted formats: .csv, .xlsx, .xls, .ods"),
    )
    import_all_sheets = forms.BooleanField(
        initial=True,
        required=False,
        label=_("Import all sheets"),
        help_text=_("For Excel/ODS files, import every sheet that contains data."),
    )
    sheet_name = forms.CharField(
        required=False,
        label=_("Sheet name (optional)"),
        help_text=_("Only used if 'Import all sheets' is unchecked."),
    )
    separator = forms.ChoiceField(
        choices=[(";", _("Semicolon")), (",", _("Comma"))],
        initial=";",
        label=_("CSV separator"),
    )
    decimal_separator = forms.ChoiceField(
        choices=[(",", _("Comma")), (".", _("Dot"))],
        initial=",",
        label=_("Decimal separator"),
    )
    date_format = forms.CharField(
        initial="%d.%m.%Y",
        label=_("Date format"),
        help_text=_("e.g. %%d.%%m.%%Y"),
    )
    time_format = forms.CharField(
        initial="%H:%M",
        label=_("Time format"),
        help_text=_("e.g. %%H:%%M"),
    )
    header_row = forms.IntegerField(
        required=False,
        min_value=0,
        label=_("Header row (0-based)"),
        help_text=_("Leave empty for auto-detection."),
    )

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop("organization", None)
        super().__init__(*args, **kwargs)
        if organization:
            self.fields["employee"].queryset = User.objects.filter(
                organization_membership__organization=organization,
                organization_membership__role="employee",
            )
            self.fields["profile"].queryset = Profile.objects.filter(
                user__organization_membership__organization=organization,
                user__organization_membership__role="employee",
            )

    def clean(self):
        cleaned_data = super().clean()
        employee = cleaned_data.get("employee")
        profile = cleaned_data.get("profile")
        if employee and profile and profile.user != employee:
            raise forms.ValidationError(_("The selected profile does not belong to the selected employee."))
        import_all = cleaned_data.get("import_all_sheets")
        sheet_name = cleaned_data.get("sheet_name")
        if not import_all and not sheet_name:
            raise forms.ValidationError(
                _("Please provide a sheet name when 'Import all sheets' is unchecked.")
            )
        return cleaned_data


class TimeEntryImportConfirmForm(forms.Form):
    """Second step: confirm and execute the import."""

    confirm = forms.BooleanField(
        required=True,
        label=_("Yes, import these entries"),
    )
    import_session_key = forms.CharField(
        widget=forms.HiddenInput(),
        required=True,
        label="",
    )


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
