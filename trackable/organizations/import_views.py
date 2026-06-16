"""Views for time-entry import."""

import uuid
from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404
from django.utils.translation import gettext_lazy as _

from trackable.organizations.decorators import org_manager_required
from trackable.organizations.forms import TimeEntryImportForm, TimeEntryImportConfirmForm
from trackable.organizations.import_parser import (
    detect_file_format,
    read_spreadsheet,
    find_header_row,
    parse_rows,
)
from trackable.organizations.models import OrganizationMembership
from trackable.profiles.models import Profile
from trackable.timetracking.models import TimeEntry


@login_required
@org_manager_required
def time_entry_import(request):
    """Import time entries from a file (step 1: upload & preview)."""
    membership = request.user.organization_membership
    organization = membership.organization

    preview_data = None

    if request.method == "POST":
        form = TimeEntryImportForm(
            request.POST, request.FILES, organization=organization
        )
        if form.is_valid():
            employee = form.cleaned_data["employee"]
            profile = form.cleaned_data["profile"]
            file = form.cleaned_data["file"]
            import_all_sheets = form.cleaned_data["import_all_sheets"]
            sheet_name = form.cleaned_data.get("sheet_name")
            decimal_separator = form.cleaned_data["decimal_separator"]
            date_format = form.cleaned_data["date_format"]
            time_format = form.cleaned_data["time_format"]
            header_row = form.cleaned_data.get("header_row")

            # Verify profile belongs to employee
            if profile.user != employee:
                messages.error(request, _("Selected profile does not belong to the selected employee."))
                return render(
                    request,
                    "organizations/time_entry_import.html",
                    {"form": form, "organization": organization},
                )

            # Detect file format
            try:
                file_format = detect_file_format(file.name)
            except ValueError as e:
                messages.error(request, str(e))
                return render(
                    request,
                    "organizations/time_entry_import.html",
                    {"form": form, "organization": organization},
                )

            # Read spreadsheet
            try:
                file.seek(0)
                sheets = read_spreadsheet(
                    file, file_format, import_all_sheets, sheet_name,
                    separator=form.cleaned_data.get("separator"),
                )
            except Exception as e:
                messages.error(
                    request,
                    _("Error reading file: %(error)s") % {"error": str(e)},
                )
                return render(
                    request,
                    "organizations/time_entry_import.html",
                    {"form": form, "organization": organization},
                )

            all_entries = []
            all_warnings = []
            all_errors = []

            for ss_name, rows in sheets:
                # Find header row (auto or configured)
                try:
                    if header_row is not None:
                        h_row = header_row
                    else:
                        h_row = find_header_row(rows)
                except ValueError as e:
                    all_errors.append(
                        _("Sheet '%(sheet)s': %(error)s")
                        % {"sheet": ss_name, "error": str(e)}
                    )
                    continue

                config = {
                    "date_col": 0,
                    "start_col": 1,
                    "end_col": 2,
                    "duration_col": 3,
                    "notes_col": 4,
                    "decimal_separator": decimal_separator,
                    "date_format": date_format,
                    "time_format": time_format,
                }

                try:
                    entries, warnings, errors = parse_rows(
                        rows, h_row, config, ss_name
                    )
                    all_entries.extend(entries)
                    all_warnings.extend(warnings)
                    all_errors.extend(errors)
                except Exception as e:
                    all_errors.append(
                        _("Error parsing sheet '%(sheet)s': %(error)s")
                        % {"sheet": ss_name, "error": str(e)}
                    )

            if all_errors:
                messages.error(
                    request,
                    _(
                        "Found %(count)d error(s) during parsing. Please fix and try again."
                    )
                    % {"count": len(all_errors)},
                )

            # Store in session
            token = str(uuid.uuid4())
            session_key = f"import_entries_{token}"
            request.session[session_key] = {
                "entries": [
                    {
                        "date": e.date.isoformat(),
                        "start_time": e.start_time.isoformat() if e.start_time else None,
                        "end_time": e.end_time.isoformat() if e.end_time else None,
                        "notes": e.notes,
                        "duration": str(e.duration) if e.duration else None,
                        "source_sheet": e.source_sheet,
                        "source_row": e.source_row,
                    }
                    for e in all_entries
                ],
                "employee_id": employee.pk,
                "profile_id": profile.pk,
                "organization_id": organization.pk,
            }

            preview_data = {
                "entries": all_entries,
                "warnings": all_warnings,
                "errors": all_errors,
                "employee": employee,
                "profile": profile,
                "token": token,
                "total_entries": len(all_entries),
            }

        # If form is invalid, fall through to render the form again
    else:
        form = TimeEntryImportForm(organization=organization)

    confirm_form = TimeEntryImportConfirmForm(
        initial={"import_session_key": preview_data["token"]}
    ) if preview_data else TimeEntryImportConfirmForm()

    return render(
        request,
        "organizations/time_entry_import.html",
        {
            "form": form,
            "confirm_form": confirm_form,
            "organization": organization,
            "preview": preview_data,
        },
    )


@login_required
@org_manager_required
def time_entry_import_confirm(request):
    """Confirm and execute the import (step 2)."""
    membership = request.user.organization_membership
    organization = membership.organization

    if request.method != "POST":
        return redirect("time_entry_import")

    form = TimeEntryImportConfirmForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Invalid confirmation."))
        return redirect("time_entry_import")

    token = form.cleaned_data["import_session_key"]
    session_key = f"import_entries_{token}"
    import_data = request.session.get(session_key)

    if not import_data:
        messages.error(
            request,
            _(
                "Import session not found. Please upload the file again."
            ),
        )
        return redirect("time_entry_import")

    # Verify data belongs to this organization
    if import_data.get("organization_id") != organization.pk:
        messages.error(request, _("Import session does not match your organization."))
        return redirect("time_entry_import")

    employee_id = import_data.get("employee_id")
    profile_id = import_data.get("profile_id")

    # Verify employee belongs to this organization
    emp_membership = get_object_or_404(
        OrganizationMembership,
        organization=organization,
        user_id=employee_id,
        role="employee",
    )
    employee = emp_membership.user

    # Verify profile belongs to this employee
    profile = get_object_or_404(Profile, pk=profile_id, user=employee)

    entries_data = import_data.get("entries", [])
    created_count = 0

    for entry_data in entries_data:
        entry_date = datetime.fromisoformat(entry_data["date"]).date()
        start_time_str = entry_data.get("start_time")
        end_time_str = entry_data.get("end_time")
        notes = entry_data.get("notes", "")

        if start_time_str:
            start_time = time.fromisoformat(start_time_str)
        else:
            start_time = time(0, 0)

        if end_time_str:
            end_time = time.fromisoformat(end_time_str)
        else:
            end_time = time(0, 0)

        TimeEntry.objects.create(
            profile=profile,
            date=entry_date,
            start_time=start_time,
            end_time=end_time,
            notes=notes,
            pause_duration=0,
        )
        created_count += 1

    # Clean up session data
    del request.session[session_key]

    messages.success(
        request,
        _("Successfully imported %(count)d time entr%(plural)s.")
        % {
            "count": created_count,
            "plural": _("ies") if created_count != 1 else _("y"),
        },
    )

    return redirect(
        "employee_profile_detail",
        user_id=employee_id,
        profile_id=profile_id,
    )
