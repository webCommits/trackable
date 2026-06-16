"""Tests for the time-entry import feature."""

import io
import os
import csv
import uuid
from datetime import date, time, datetime, timedelta

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from trackable.organizations.models import Organization, OrganizationMembership
from trackable.profiles.models import Profile
from trackable.timetracking.models import TimeEntry
from trackable.organizations.import_parser import (
    ParsedEntry,
    detect_file_format,
    find_header_row,
    is_summary_row,
    parse_rows,
    read_spreadsheet,
)

User = get_user_model()


def _create_org_with_employee():
    """Helper: create an org with a manager and an employee (with profile)."""
    manager = User.objects.create_user(
        username="importmgr", email="mgr@example.com", password="pass123"
    )
    org = Organization.objects.create(name="ImportCorp", created_by=manager)
    OrganizationMembership.objects.create(
        organization=org, user=manager, role="manager"
    )

    employee = User.objects.create_user(
        username="importemp", email="emp@example.com", password="pass123"
    )
    OrganizationMembership.objects.create(
        organization=org, user=employee, role="employee"
    )
    profile = Profile.objects.create(
        user=employee,
        title="Developer",
        position="Dev",
        weekly_hours=40,
        hourly_rate=50,
    )
    return org, manager, employee, profile


def _make_csv_bytes(rows, delimiter=";"):
    """Create CSV bytes from a list of row lists."""
    output = io.StringIO()
    writer = csv.writer(output, delimiter=delimiter)
    for row in rows:
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


class DetectFileFormatTest(TestCase):
    def test_csv(self):
        self.assertEqual(detect_file_format("data.csv"), "csv")
        self.assertEqual(detect_file_format("data.CSV"), "csv")

    def test_xlsx(self):
        self.assertEqual(detect_file_format("data.xlsx"), "xlsx")

    def test_xls(self):
        self.assertEqual(detect_file_format("data.xls"), "xls")

    def test_ods(self):
        self.assertEqual(detect_file_format("data.ods"), "ods")

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            detect_file_format("data.txt")
        with self.assertRaises(ValueError):
            detect_file_format("data.pdf")


class FindHeaderRowTest(TestCase):
    def test_find_header(self):
        rows = [
            ["Some title", ""],
            [""],
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["13.07.2025", "17:15", "18:45", "1,50", "Work"],
        ]
        self.assertEqual(find_header_row(rows), 2)

    def test_not_found_raises(self):
        rows = [["Name", "Value"], ["foo", "bar"]]
        with self.assertRaises(ValueError):
            find_header_row(rows)


class IsSummaryRowTest(TestCase):
    def test_ist(self):
        self.assertTrue(is_summary_row(["", "Ist", "26,00"]))

    def test_soll(self):
        self.assertTrue(is_summary_row(["", "Soll", "26,00"]))

    def test_ubertrag(self):
        self.assertTrue(is_summary_row(["", "Übertrag aus Vormonat", "-10,50"]))

    def test_uber_unterdeckung(self):
        self.assertTrue(is_summary_row(["", "Über-/ Unterdeckung", "-10,50"]))

    def test_normal_row(self):
        self.assertFalse(is_summary_row(["13.07.2025", "17:15", "18:45", "1,50", "Work"]))

    def test_empty_row(self):
        self.assertFalse(is_summary_row(["", "", ""]))


class ParseRowsTest(TestCase):
    def test_basic_parsing(self):
        rows = [
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["13.07.2025", "17:15", "18:45", "1,50", "VZP Aachen"],
        ]
        entries, warnings, errors = parse_rows(rows, header_row=0, sheet_name="Juli 2025")
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(len(errors), 0)
        e = entries[0]
        self.assertEqual(e.date, date(2025, 7, 13))
        self.assertEqual(e.start_time, time(17, 15))
        self.assertEqual(e.end_time, time(18, 45))
        self.assertEqual(e.notes, "VZP Aachen")

    def test_multiple_entries_same_date(self):
        rows = [
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["01.09.2025", "10:00", "11:15", "1,50", "Work A"],
            ["01.09.2025", "12:00", "13:30", "1,50", "Work B"],
        ]
        entries, _, _ = parse_rows(rows, header_row=0)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].date, date(2025, 9, 1))
        self.assertEqual(entries[1].date, date(2025, 9, 1))
        self.assertEqual(entries[0].notes, "Work A")
        self.assertEqual(entries[1].notes, "Work B")

    def test_stundengutschrift(self):
        rows = [
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["24.12.2025", "", "", "10,00", "Stundengutschrift"],
        ]
        entries, warnings, errors = parse_rows(rows, header_row=0)
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(errors), 0)
        e = entries[0]
        self.assertEqual(e.date, date(2025, 12, 24))
        self.assertEqual(e.start_time, time(0, 0))
        self.assertEqual(e.end_time, time(10, 0))
        self.assertIn("Stundengutschrift", e.notes)

    def test_stundengutschrift_empty_notes(self):
        rows = [
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["24.12.2025", "", "", "8,00", ""],
        ]
        entries, warnings, errors = parse_rows(rows, header_row=0)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e.start_time, time(0, 0))
        self.assertEqual(e.end_time, time(8, 0))

    def test_stundengutschrift_overflow_24h(self):
        rows = [
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["24.12.2025", "", "", "24,00", "Too much"],
        ]
        entries, warnings, errors = parse_rows(rows, header_row=0)
        self.assertEqual(len(entries), 0)
        self.assertEqual(len(errors), 1)

    def test_empty_then_summary_rows_skipped(self):
        rows = [
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["13.07.2025", "17:15", "18:45", "1,50", "Work"],
            ["", "", "", "", ""],
            ["", "Ist", "26,00", ""],
            ["", "Soll", "26,00", ""],
        ]
        entries, warnings, errors = parse_rows(rows, header_row=0)
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(errors), 0)

    def test_duration_warning(self):
        rows = [
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["13.07.2025", "17:00", "19:00", "3,00", "Work"],
        ]
        entries, warnings, errors = parse_rows(rows, header_row=0)
        self.assertEqual(len(entries), 1)
        # 19:00-17:00 = 2h, but file says 3h -> diff=1h > 0.25
        self.assertEqual(len(warnings), 1)

    def test_year_mismatch_warning(self):
        rows = [
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["09.01.2025", "10:45", "12:45", "2,00", "Work"],
        ]
        entries, warnings, errors = parse_rows(rows, header_row=0, sheet_name="Januar 2026")
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(warnings), 1)
        self.assertIn("year", warnings[0].lower())

    def test_decimal_separator_dot(self):
        rows = [
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["13.07.2025", "17:15", "18:45", "1.50", "Work"],
        ]
        config = {"decimal_separator": "."}
        entries, warnings, errors = parse_rows(rows, header_row=0, config=config)
        self.assertEqual(len(entries), 1)

    def test_no_start_end_no_duration_skipped(self):
        rows = [
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["13.07.2025", "", "", "", ""],
        ]
        entries, warnings, errors = parse_rows(rows, header_row=0)
        self.assertEqual(len(entries), 0)
        self.assertEqual(len(warnings), 1)

    def test_cross_midnight(self):
        rows = [
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["13.07.2025", "22:00", "01:00", "3,00", "Night work"],
        ]
        entries, _, _ = parse_rows(rows, header_row=0)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e.start_time, time(22, 0))
        self.assertEqual(e.end_time, time(1, 0))


class CSVImportTest(TestCase):
    def test_csv_parsing(self):
        csv_data = _make_csv_bytes([
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["01.06.2026", "08:00", "12:00", "4,00", "Morning work"],
            ["01.06.2026", "13:00", "17:00", "4,00", "Afternoon work"],
        ])
        file = SimpleUploadedFile("test.csv", csv_data, content_type="text/csv")
        sheets = read_spreadsheet(file, "csv")
        self.assertEqual(len(sheets), 1)
        self.assertEqual(sheets[0][0], "CSV")
        rows = sheets[0][1]
        self.assertEqual(len(rows), 3)  # header + 2 data rows

    def test_csv_with_semicolon(self):
        csv_data = _make_csv_bytes([
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["01.06.2026", "08:00", "12:00", "4,00", "Work"],
        ], delimiter=";")
        file = SimpleUploadedFile("test.csv", csv_data, content_type="text/csv")
        sheets = read_spreadsheet(file, "csv")
        rows = sheets[0][1]
        self.assertEqual(rows[1][0], "01.06.2026")
        self.assertEqual(rows[1][4], "Work")


class ODSImportTest(TestCase):
    """Test importing the test fixture ODS file."""

    def _fixture_path(self):
        import os
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "fixtures",
            "test_import.ods",
        )

    def test_parse_fixture(self):
        """Test that the parser can handle the test fixture ODS file."""
        file_path = self._fixture_path()
        self.assertTrue(
            os.path.exists(file_path),
            f"Fixture file not found at {file_path}",
        )

        with open(file_path, "rb") as f:
            sheets = read_spreadsheet(f, "ods", import_all_sheets=True)

        # Should have 2 sheets (Januar 2026, Februar 2026)
        self.assertEqual(len(sheets), 2)

        # Parse all sheets
        all_entries = []
        all_warnings = []
        all_errors = []

        for sheet_name, rows in sheets:
            header_row = find_header_row(rows)
            entries, warnings, errors = parse_rows(
                rows, header_row, {}, sheet_name
            )
            all_entries.extend(entries)
            all_warnings.extend(warnings)
            all_errors.extend(errors)

        # We should find entries
        self.assertGreater(len(all_entries), 0, "Should find entries in the ODS file")

        # Check Stundengutschrift row exists
        gutschrift_entries = [
            e for e in all_entries
            if "Stundengutschrift" in e.notes
        ]
        self.assertEqual(
            len(gutschrift_entries), 1,
            "Should find exactly 1 Stundengutschrift entry",
        )

    def test_upload_and_preview_fixture(self):
        """Integration test: upload the test fixture ODS file via the import view."""
        org, manager, employee, profile = _create_org_with_employee()
        self.client.login(username="importmgr", password="pass123")

        file_path = self._fixture_path()

        with open(file_path, "rb") as f:
            response = self.client.post(
                reverse("time_entry_import"),
                {
                    "employee": employee.pk,
                    "profile": profile.pk,
                    "file": f,
                    "import_all_sheets": True,
                    "separator": ";",
                    "decimal_separator": ",",
                    "date_format": "%d.%m.%Y",
                    "time_format": "%H:%M",
                },
            )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        # Verify we got preview data (not an invalid form)
        self.assertIn("Import summary", content)

    def test_confirm_import_fixture(self):
        """Integration test: upload, preview, confirm the test fixture ODS file."""
        org, manager, employee, profile = _create_org_with_employee()
        self.client.login(username="importmgr", password="pass123")

        file_path = self._fixture_path()

        # Step 1: Upload
        with open(file_path, "rb") as f:
            response = self.client.post(
                reverse("time_entry_import"),
                {
                    "employee": employee.pk,
                    "profile": profile.pk,
                    "file": f,
                    "import_all_sheets": True,
                    "separator": ";",
                    "decimal_separator": ",",
                    "date_format": "%d.%m.%Y",
                    "time_format": "%H:%M",
                },
            )
        self.assertEqual(response.status_code, 200)

        # Extract token from the session
        token = None
        for key in self.client.session.keys():
            if key.startswith("import_entries_"):
                token = key[len("import_entries_"):]
                break
        self.assertIsNotNone(token, "Import session key should exist")

        # Count entries in session
        session_key = f"import_entries_{token}"
        import_data = self.client.session[session_key]
        num_entries = len(import_data["entries"])
        self.assertGreater(num_entries, 0, "Should have parsed entries")

        # Step 2: Confirm
        response = self.client.post(
            reverse("time_entry_import_confirm"),
            {
                "confirm": True,
                "import_session_key": token,
            },
        )

        # Should redirect to employee_profile_detail
        self.assertEqual(response.status_code, 302)
        expected_url = reverse(
            "employee_profile_detail",
            kwargs={"user_id": employee.pk, "profile_id": profile.pk},
        )
        self.assertEqual(response.url, expected_url)

        # Check entries were created
        created_entries = TimeEntry.objects.filter(profile=profile)
        self.assertEqual(created_entries.count(), num_entries)


class ImportViewAccessTest(TestCase):
    def test_manager_can_access_import(self):
        org, manager, employee, profile = _create_org_with_employee()
        self.client.login(username="importmgr", password="pass123")
        response = self.client.get(reverse("time_entry_import"))
        self.assertEqual(response.status_code, 200)

    def test_employee_redirected(self):
        org, manager, employee, profile = _create_org_with_employee()
        self.client.login(username="importemp", password="pass123")
        response = self.client.get(reverse("time_entry_import"))
        self.assertEqual(response.status_code, 302)

    def test_import_other_org_employee_fails(self):
        """Manager of org A cannot import for employee of org B."""
        org, manager, employee, profile = _create_org_with_employee()

        # Create another org
        other_mgr = User.objects.create_user(
            username="othermgr", password="pass123"
        )
        other_org = Organization.objects.create(
            name="OtherCorp", created_by=other_mgr
        )
        OrganizationMembership.objects.create(
            organization=other_org, user=other_mgr, role="manager"
        )

        self.client.login(username="othermgr", password="pass123")

        # Try to upload for an employee of the other org (should not appear in queryset)
        response = self.client.post(
            reverse("time_entry_import"),
            {
                "employee": employee.pk,
                "profile": profile.pk,
                "file": SimpleUploadedFile(
                    "test.csv",
                    _make_csv_bytes([
                        ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
                        ["01.06.2026", "08:00", "12:00", "4,00", "Work"],
                    ]),
                    content_type="text/csv",
                ),
                "import_all_sheets": True,
                "separator": ";",
                "decimal_separator": ",",
                "date_format": "%d.%m.%Y",
                "time_format": "%H:%M",
            },
        )
        # The form validation should fail because the employee is not in the queryset
        # or the profile doesn't belong to the employee in the org
        self.assertEqual(response.status_code, 200)
        # The form should have validation errors
        self.assertIn("form", response.context)


class ImportCSVIntegrationTest(TestCase):
    def test_csv_import_flow(self):
        """Full CSV import flow: upload, preview, confirm."""
        org, manager, employee, profile = _create_org_with_employee()
        self.client.login(username="importmgr", password="pass123")

        csv_data = _make_csv_bytes([
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["01.06.2026", "08:00", "12:00", "4,00", "Morning"],
            ["01.06.2026", "13:00", "17:00", "4,00", "Afternoon"],
            ["02.06.2026", "09:00", "13:00", "4,00", "Day 2"],
        ])

        # Step 1: Upload
        response = self.client.post(
            reverse("time_entry_import"),
            {
                "employee": employee.pk,
                "profile": profile.pk,
                "file": SimpleUploadedFile(
                    "test.csv", csv_data, content_type="text/csv"
                ),
                "import_all_sheets": True,
                "separator": ";",
                "decimal_separator": ",",
                "date_format": "%d.%m.%Y",
                "time_format": "%H:%M",
            },
        )
        self.assertEqual(response.status_code, 200)

        # Extract token
        token = None
        for key in self.client.session.keys():
            if key.startswith("import_entries_"):
                token = key[len("import_entries_"):]
                break
        self.assertIsNotNone(token)

        # Step 2: Confirm
        response = self.client.post(
            reverse("time_entry_import_confirm"),
            {
                "confirm": True,
                "import_session_key": token,
            },
        )
        self.assertEqual(response.status_code, 302)

        # Check entries
        entries = TimeEntry.objects.filter(profile=profile).order_by("date", "start_time")
        self.assertEqual(entries.count(), 3)
        self.assertEqual(entries[0].date, date(2026, 6, 1))
        self.assertEqual(entries[0].start_time, time(8, 0))
        self.assertEqual(entries[0].end_time, time(12, 0))
        self.assertEqual(entries[0].notes, "Morning")

    def test_stundengutschrift_import(self):
        """Import a CSV with a Stundengutschrift row."""
        org, manager, employee, profile = _create_org_with_employee()
        self.client.login(username="importmgr", password="pass123")

        csv_data = _make_csv_bytes([
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["24.12.2025", "", "", "10,00", "Stundengutschrift"],
            ["28.12.2025", "10:30", "12:30", "2,00", "Normal work"],
        ])

        # Step 1: Upload
        response = self.client.post(
            reverse("time_entry_import"),
            {
                "employee": employee.pk,
                "profile": profile.pk,
                "file": SimpleUploadedFile(
                    "test.csv", csv_data, content_type="text/csv"
                ),
                "import_all_sheets": True,
                "separator": ";",
                "decimal_separator": ",",
                "date_format": "%d.%m.%Y",
                "time_format": "%H:%M",
            },
        )
        self.assertEqual(response.status_code, 200)

        token = None
        for key in self.client.session.keys():
            if key.startswith("import_entries_"):
                token = key[len("import_entries_"):]
                break
        self.assertIsNotNone(token)

        # Verify Stundengutschrift was parsed
        import_data = self.client.session[f"import_entries_{token}"]
        entries_data = import_data["entries"]
        gutschrift = [e for e in entries_data if "Stundengutschrift" in e.get("notes", "")]
        self.assertEqual(len(gutschrift), 1)
        self.assertEqual(gutschrift[0]["start_time"], "00:00:00")
        self.assertEqual(gutschrift[0]["end_time"], "10:00:00")

        # Step 2: Confirm
        response = self.client.post(
            reverse("time_entry_import_confirm"),
            {
                "confirm": True,
                "import_session_key": token,
            },
        )
        self.assertEqual(response.status_code, 302)

        entries = TimeEntry.objects.filter(profile=profile).order_by("date")
        self.assertEqual(entries.count(), 2)
        gutschrift_entry = entries.get(date=date(2025, 12, 24))
        self.assertEqual(gutschrift_entry.start_time, time(0, 0))
        self.assertEqual(gutschrift_entry.end_time, time(10, 0))

    def test_decimal_separator_dot_import(self):
        """Import a CSV with decimal separator dot."""
        org, manager, employee, profile = _create_org_with_employee()
        self.client.login(username="importmgr", password="pass123")

        csv_data = _make_csv_bytes([
            ["Datum", "Beginn", "Ende", "Dauer", "Art der Arbeit"],
            ["01.06.2026", "08:00", "12:00", "4.00", "Work"],
        ])

        response = self.client.post(
            reverse("time_entry_import"),
            {
                "employee": employee.pk,
                "profile": profile.pk,
                "file": SimpleUploadedFile(
                    "test.csv", csv_data, content_type="text/csv"
                ),
                "import_all_sheets": True,
                "separator": ";",
                "decimal_separator": ".",
                "date_format": "%d.%m.%Y",
                "time_format": "%H:%M",
            },
        )
        self.assertEqual(response.status_code, 200)

        token = None
        for key in self.client.session.keys():
            if key.startswith("import_entries_"):
                token = key[len("import_entries_"):]
                break
        self.assertIsNotNone(token)

        response = self.client.post(
            reverse("time_entry_import_confirm"),
            {
                "confirm": True,
                "import_session_key": token,
            },
        )
        self.assertEqual(response.status_code, 302)

        entries = TimeEntry.objects.filter(profile=profile)
        self.assertEqual(entries.count(), 1)


class ReadSpreadsheetTest(TestCase):
    def test_csv_read(self):
        csv_data = _make_csv_bytes([
            ["Datum", "Beginn"],
            ["01.06.2026", "08:00"],
        ])
        file = SimpleUploadedFile("test.csv", csv_data, content_type="text/csv")
        sheets = read_spreadsheet(file, "csv")
        self.assertEqual(len(sheets), 1)
        self.assertEqual(sheets[0][0], "CSV")
        self.assertEqual(len(sheets[0][1]), 2)

    def test_csv_ignores_sheet_name(self):
        csv_data = _make_csv_bytes([
            ["Datum", "Beginn"],
            ["01.06.2026", "08:00"],
        ])
        file = SimpleUploadedFile("test.csv", csv_data, content_type="text/csv")
        sheets = read_spreadsheet(file, "csv", import_all_sheets=False, sheet_name="MySheet")
        self.assertEqual(len(sheets), 1)
        self.assertEqual(sheets[0][0], "CSV")

    def test_unknown_format_raises(self):
        file = SimpleUploadedFile("test.txt", b"data", content_type="text/plain")
        with self.assertRaises(ValueError):
            read_spreadsheet(file, "txt")
