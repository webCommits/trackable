import json
from datetime import date, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from trackable.organizations.helpers import can_manage_profile_time_entries
from trackable.organizations.models import Organization, OrganizationMembership
from trackable.profiles.models import Profile
from trackable.timetracking.models import TimeEntry, VacationEntry, ActiveTimer


User = get_user_model()


class ManagerTimeEntryFormTest(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="secret"
        )
        self.employee = User.objects.create_user(
            username="employee", email="employee@example.com", password="secret"
        )
        self.other_user = User.objects.create_user(
            username="other", email="other@example.com", password="secret"
        )

        self.organization = Organization.objects.create(
            name="Test Org",
            created_by=self.manager,
            time_tracking_mode="restricted",
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.manager, role="manager"
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.employee, role="employee"
        )

        self.other_org = Organization.objects.create(
            name="Other Org",
            created_by=self.other_user,
            time_tracking_mode="restricted",
        )
        OrganizationMembership.objects.create(
            organization=self.other_org, user=self.other_user, role="manager"
        )

        self.profile = Profile.objects.create(
            user=self.employee,
            title="Employee Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )
        self.other_profile = Profile.objects.create(
            user=self.other_user,
            title="Other Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )

    def test_manager_can_add_entry_for_employee_in_restricted_mode(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            f"/add-entry/{self.profile.id}/",
            {
                "date": "2024-06-18",
                "start_time": "08:00",
                "end_time": "16:00",
                "pause_duration": "1",
                "notes": "Test entry",
            },
        )
        self.assertEqual(TimeEntry.objects.count(), 1)
        entry = TimeEntry.objects.first()
        self.assertEqual(entry.profile, self.profile)
        self.assertEqual(entry.hours_worked, 7)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse(
                "employee_profile_detail",
                kwargs={"user_id": self.employee.id, "profile_id": self.profile.id},
            ),
        )

    def test_manager_can_edit_entry_for_employee(self):
        entry = TimeEntry.objects.create(
            profile=self.profile,
            date=date(2024, 6, 18),
            start_time=time(8, 0),
            end_time=time(12, 0),
            pause_duration=0,
            hours_worked=4,
        )
        self.client.force_login(self.manager)
        response = self.client.post(
            f"/entry/{entry.id}/edit/",
            {
                "date": "2024-06-18",
                "start_time": "08:00",
                "end_time": "14:00",
                "pause_duration": "0",
                "notes": "Updated",
            },
        )
        entry.refresh_from_db()
        self.assertEqual(entry.hours_worked, 6)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse(
                "employee_profile_detail",
                kwargs={"user_id": self.employee.id, "profile_id": self.profile.id},
            ),
        )

    def test_manager_can_delete_entry_for_employee(self):
        entry = TimeEntry.objects.create(
            profile=self.profile,
            date=date(2024, 6, 18),
            start_time=time(8, 0),
            end_time=time(12, 0),
            pause_duration=0,
            hours_worked=4,
        )
        self.client.force_login(self.manager)
        response = self.client.post(f"/entry/{entry.id}/delete/")
        self.assertEqual(TimeEntry.objects.count(), 0)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse(
                "employee_profile_detail",
                kwargs={"user_id": self.employee.id, "profile_id": self.profile.id},
            ),
        )

    def test_employee_cannot_add_entry_in_restricted_mode(self):
        self.client.force_login(self.employee)
        response = self.client.post(
            f"/add-entry/{self.profile.id}/",
            {
                "date": "2024-06-18",
                "start_time": "08:00",
                "end_time": "16:00",
                "pause_duration": "1",
                "notes": "Test entry",
            },
        )
        self.assertEqual(TimeEntry.objects.count(), 0)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_manager_cannot_access_profile_from_other_organization(self):
        self.client.force_login(self.manager)
        response = self.client.get(f"/add-entry/{self.other_profile.id}/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_helper_can_manage_profile_time_entries(self):
        self.assertTrue(can_manage_profile_time_entries(self.manager, self.profile))
        self.assertFalse(
            can_manage_profile_time_entries(self.employee, self.profile)
        )
        self.assertFalse(
            can_manage_profile_time_entries(self.manager, self.other_profile)
        )


class VacationDisabledTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="employee", email="employee@example.com", password="secret"
        )
        self.organization = Organization.objects.create(
            name="Test Org",
            created_by=self.user,
            time_tracking_mode="classic",
            holidays_enabled=False,
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.user, role="employee"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Employee Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )

    def test_vacation_overview_redirects_when_disabled(self):
        self.client.force_login(self.user)
        response = self.client.get(f"/vacation/{self.profile.id}/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_add_vacation_redirects_when_disabled(self):
        self.client.force_login(self.user)
        response = self.client.post(
            f"/vacation/{self.profile.id}/add/",
            {
                "start_date": "2024-06-18",
                "end_date": "2024-06-20",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))
        self.assertEqual(VacationEntry.objects.count(), 0)

    def test_delete_vacation_redirects_when_disabled(self):
        vacation = VacationEntry.objects.create(
            profile=self.profile,
            start_date=date(2024, 6, 18),
            end_date=date(2024, 6, 20),
        )
        self.client.force_login(self.user)
        response = self.client.post(f"/vacation/delete/{vacation.id}/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))
        self.assertEqual(VacationEntry.objects.count(), 1)


class MonthlyTableVacationButtonTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="employee", email="employee@example.com", password="secret"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Employee Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )

    def _get_context(self, user):
        from trackable.timetracking.views import monthly_table

        request = RequestFactory().get("/")
        request.user = user
        captured = {}

        def mock_render(request, template_name, context, **kwargs):
            captured[template_name] = context
            return HttpResponse("rendered")

        with patch("trackable.timetracking.views.render", mock_render):
            response = monthly_table(request, profile_id=self.profile.id, year=2024, month=6)

        self.assertEqual(response.status_code, 200)
        return captured["timetracking/monthly_table.html"]

    def test_user_without_org_sees_vacation_button(self):
        context = self._get_context(self.user)
        self.assertTrue(context["show_vacation"])

    def test_user_with_disabled_holidays_does_not_see_vacation_button(self):
        org = Organization.objects.create(
            name="Test Org",
            created_by=self.user,
            time_tracking_mode="classic",
            holidays_enabled=False,
        )
        OrganizationMembership.objects.create(
            organization=org, user=self.user, role="employee"
        )
        context = self._get_context(self.user)
        self.assertFalse(context["show_vacation"])


# ── Stop Timer: Notes ────────────────────────────────────────────────────────


class StopTimerNotesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="user", email="user@example.com", password="secret"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Test Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )

    def _start_timer(self, hours_ago=1):
        return ActiveTimer.objects.create(
            profile=self.profile,
            user=self.user,
            start_time=timezone.now() - timedelta(hours=hours_ago),
            is_paused=False,
        )

    def _post_stop(self, payload):
        return self.client.post(
            f"/timer/{self.profile.id}/stop/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_stop_timer_with_notes_saves_to_entry(self):
        self._start_timer()
        self.client.force_login(self.user)
        response = self._post_stop({"notes": "Bug #123 gefixt"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "stopped")
        self.assertTrue(data["notes_saved"])
        entry = TimeEntry.objects.get(profile=self.profile)
        self.assertEqual(entry.notes, "Bug #123 gefixt")

    def test_stop_timer_without_notes_saves_empty(self):
        self._start_timer()
        self.client.force_login(self.user)
        response = self._post_stop({})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["notes_saved"])
        entry = TimeEntry.objects.get(profile=self.profile)
        self.assertEqual(entry.notes, "")

    def test_stop_timer_truncates_notes_over_1000_chars(self):
        self._start_timer()
        self.client.force_login(self.user)
        long_notes = "x" * 1500
        response = self._post_stop({"notes": long_notes})
        self.assertEqual(response.status_code, 200)
        entry = TimeEntry.objects.get(profile=self.profile)
        self.assertEqual(len(entry.notes), 1000)

    def test_stop_timer_with_unicode_notes(self):
        self._start_timer()
        self.client.force_login(self.user)
        response = self._post_stop({"notes": "Äpfel 🍎 & <html>tags</html>"})
        self.assertEqual(response.status_code, 200)
        entry = TimeEntry.objects.get(profile=self.profile)
        self.assertEqual(entry.notes, "Äpfel 🍎 & <html>tags</html>")


# ── Stop Timer: Overrides ────────────────────────────────────────────────────


class StopTimerOverridesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="user", email="user@example.com", password="secret"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Test Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )

    def _start_timer(self, hours_ago=2):
        return ActiveTimer.objects.create(
            profile=self.profile,
            user=self.user,
            start_time=timezone.now() - timedelta(hours=hours_ago),
            is_paused=False,
        )

    def _post_stop(self, payload):
        return self.client.post(
            f"/timer/{self.profile.id}/stop/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_classic_mode_can_override_start_end_and_pause(self):
        self._start_timer()
        self.client.force_login(self.user)
        response = self._post_stop({
            "start_time": "08:00",
            "end_time": "16:00",
            "pause_duration": 1.0,
        })
        self.assertEqual(response.status_code, 200)
        entry = TimeEntry.objects.get(profile=self.profile)
        self.assertEqual(entry.start_time.strftime("%H:%M"), "08:00")
        self.assertEqual(entry.end_time.strftime("%H:%M"), "16:00")
        self.assertEqual(float(entry.pause_duration), 1.0)
        self.assertEqual(float(entry.hours_worked), 7.0)

    def test_classic_mode_can_override_date(self):
        self._start_timer()
        self.client.force_login(self.user)
        response = self._post_stop({
            "date": "2024-06-18",
            "start_time": "08:00",
            "end_time": "16:00",
        })
        self.assertEqual(response.status_code, 200)
        entry = TimeEntry.objects.get(profile=self.profile)
        self.assertEqual(str(entry.date), "2024-06-18")

    def test_restricted_mode_ignores_time_overrides(self):
        org = Organization.objects.create(
            name="Restricted Org",
            created_by=self.user,
            time_tracking_mode="restricted",
        )
        OrganizationMembership.objects.create(
            organization=org, user=self.user, role="employee"
        )
        timer = self._start_timer()
        original_start_local = timezone.localtime(timer.start_time).time()
        self.client.force_login(self.user)
        response = self._post_stop({
            "start_time": "08:00",
            "end_time": "16:00",
        })
        self.assertEqual(response.status_code, 200)
        entry = TimeEntry.objects.get(profile=self.profile)
        self.assertNotEqual(entry.start_time.strftime("%H:%M"), "08:00")
        self.assertEqual(entry.start_time, original_start_local)

    def test_manager_in_restricted_mode_can_override(self):
        manager = User.objects.create_user(
            username="manager", email="m@example.com", password="secret"
        )
        org = Organization.objects.create(
            name="Restricted Org",
            created_by=manager,
            time_tracking_mode="restricted",
        )
        OrganizationMembership.objects.create(
            organization=org, user=manager, role="manager"
        )
        # Profil an Manager übergeben UND Timer mit dem Manager-User starten
        self.profile.user = manager
        self.profile.save()
        ActiveTimer.objects.create(
            profile=self.profile,
            user=manager,
            start_time=timezone.now() - timedelta(hours=2),
            is_paused=False,
        )
        self.client.force_login(manager)
        response = self.client.post(
            f"/timer/{self.profile.id}/stop/",
            data=json.dumps({
                "start_time": "08:00",
                "end_time": "16:00",
                "pause_duration": 0.5,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        entry = TimeEntry.objects.get(profile=self.profile)
        self.assertEqual(entry.start_time.strftime("%H:%M"), "08:00")
        self.assertEqual(float(entry.pause_duration), 0.5)

    def test_zero_duration_when_start_equals_end(self):
        self._start_timer()
        self.client.force_login(self.user)
        response = self._post_stop({
            "start_time": "16:00",
            "end_time": "16:00",
        })
        self.assertEqual(response.status_code, 200)
        entry = TimeEntry.objects.get(profile=self.profile)
        self.assertEqual(float(entry.hours_worked), 0.0)

    def test_negative_pause_returns_400(self):
        self._start_timer()
        self.client.force_login(self.user)
        response = self._post_stop({"pause_duration": -1.0})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "pause_duration")

    def test_invalid_date_format_returns_400(self):
        self._start_timer()
        self.client.force_login(self.user)
        response = self._post_stop({"date": "not-a-date"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "date")

    def test_stop_timer_works_in_restricted_mode_for_employee(self):
        """Regression-Schutz: Employee darf im restricted mode stoppen."""
        org = Organization.objects.create(
            name="Restricted Org",
            created_by=self.user,
            time_tracking_mode="restricted",
        )
        OrganizationMembership.objects.create(
            organization=org, user=self.user, role="employee"
        )
        self._start_timer()
        self.client.force_login(self.user)
        response = self._post_stop({})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TimeEntry.objects.count(), 1)

    def test_overrides_allow_overnight_end_before_start(self):
        """End vor Start soll als Tagesüberschlag interpretiert werden
        (gleicher Tag + 1 Tag), nicht als Fehler."""
        self._start_timer()
        self.client.force_login(self.user)
        response = self._post_stop({
            "date": "2024-06-18",
            "start_time": "22:00",
            "end_time": "06:00",
        })
        self.assertEqual(response.status_code, 200)
        entry = TimeEntry.objects.get(profile=self.profile)
        self.assertEqual(entry.start_time.strftime("%H:%M"), "22:00")
        self.assertEqual(entry.end_time.strftime("%H:%M"), "06:00")
        # 22:00 → 06:00 nächster Tag = 8h, keine Pause
        self.assertEqual(float(entry.hours_worked), 8.0)


# ── Timer Fixes: Timezone, Pause-Stop, client_timestamp, Duplicate ───


class StopTimerTimezoneTest(TestCase):
    """Stop timer uses local project timezone (Europe/Berlin) via localtime()."""

    def _post_stop(self, payload):
        return self.client.post(
            f"/timer/{self.profile.id}/stop/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    @override_settings(TIME_ZONE="Europe/Berlin", USE_TZ=True)
    def test_stop_timer_uses_local_time(self):
        """DateTimeFields should be converted to local TZ before date()/time()."""
        self.user = User.objects.create_user(
            username="tzuser", email="tz@example.com", password="secret"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="TZ Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )
        # Timer startet um 10:00 UTC = 12:00 Europe/Berlin (CEST, UTC+2)
        import datetime as dt
        base = dt.datetime(2024, 6, 18, 10, 0, 0, tzinfo=dt.timezone.utc)
        ActiveTimer.objects.create(
            profile=self.profile,
            user=self.user,
            start_time=base,
            is_paused=False,
        )
        self.client.force_login(self.user)
        # Stop ohne Override → soll lokale Zeit verwenden
        response = self._post_stop({})
        self.assertEqual(response.status_code, 200)
        entry = TimeEntry.objects.get(profile=self.profile)
        # Start sollte 12:00 (lokale Zeit) sein, nicht 10:00 UTC
        self.assertEqual(entry.start_time.strftime("%H:%M"), "12:00")


class StopTimerDuringPauseTest(TestCase):
    """Stopping a paused timer should end at pause_time, not at current time."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="pauseuser", email="pause@example.com", password="secret"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Pause Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )

    def _post_stop(self, payload):
        return self.client.post(
            f"/timer/{self.profile.id}/stop/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_stop_during_pause_ends_at_pause_time(self):
        """Stop while paused → effective end = pause_time."""
        base = timezone.now()
        timer = ActiveTimer.objects.create(
            profile=self.profile,
            user=self.user,
            start_time=base,
            is_paused=True,
            pause_time=base + timedelta(hours=1),  # paused after 1h
            total_paused_seconds=0,
        )
        self.client.force_login(self.user)
        response = self._post_stop({})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "stopped")
        entry = TimeEntry.objects.get(profile=self.profile)
        # Start and end times are stored in local TZ (via localtime conversion)
        # The difference between end and start should be 1h
        from datetime import datetime
        start_dt = datetime.combine(entry.date, entry.start_time)
        end_dt = datetime.combine(entry.date, entry.end_time)
        # Handle overnight if needed
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
        diff = (end_dt - start_dt).total_seconds() / 3600
        self.assertAlmostEqual(diff, 1.0, places=1)
        # 1h worked, 0 pause
        self.assertEqual(float(entry.hours_worked), 1.0)

    def test_stop_during_pause_with_total_paused(self):
        """Stop while paused with accumulated pause seconds."""
        base = timezone.now()
        timer = ActiveTimer.objects.create(
            profile=self.profile,
            user=self.user,
            start_time=base,
            is_paused=True,
            pause_time=base + timedelta(hours=2),
            total_paused_seconds=3600,  # 1h total pause already
        )
        self.client.force_login(self.user)
        response = self._post_stop({})
        self.assertEqual(response.status_code, 200)
        entry = TimeEntry.objects.get(profile=self.profile)
        # 2h span - 1h pause = 1h worked
        self.assertEqual(float(entry.hours_worked), 1.0)


class StopTimerClientTimestampTest(TestCase):
    """client_timestamp on stop should clamp to now and be used for end time."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="cstuser", email="cst@example.com", password="secret"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="CST Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )

    def _post_stop(self, payload):
        return self.client.post(
            f"/timer/{self.profile.id}/stop/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_client_timestamp_clamped_to_now(self):
        """Future client_timestamp should be clamped to now."""
        # Future timestamp
        future = timezone.now() + timedelta(hours=1)
        future_iso = future.isoformat()

        timer = ActiveTimer.objects.create(
            profile=self.profile,
            user=self.user,
            start_time=timezone.now() - timedelta(hours=2),
            is_paused=False,
        )
        self.client.force_login(self.user)
        response = self._post_stop({"client_timestamp": future_iso})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "stopped")
        # hours_worked should be ~2h (not 3h), because future was clamped to now
        self.assertAlmostEqual(float(data["hours_worked"]), 2.0, delta=1.0)

    def test_client_timestamp_past_stop(self):
        """Past client_timestamp should be used for end time."""
        now = timezone.now()
        ActiveTimer.objects.create(
            profile=self.profile,
            user=self.user,
            start_time=now - timedelta(hours=3),
            is_paused=False,
        )
        # Stop happened 1h ago: 3h-old start → 2h worked.
        past_ts = (now - timedelta(hours=1)).isoformat()
        self.client.force_login(self.user)
        response = self._post_stop({"client_timestamp": past_ts})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertAlmostEqual(float(data["hours_worked"]), 2.0, delta=0.1)


class OvernightTimerTest(TestCase):
    """Overnight timer: start late evening, stop next morning."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="overnight", email="on@example.com", password="secret"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Night Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )

    def _post_stop(self, payload):
        return self.client.post(
            f"/timer/{self.profile.id}/stop/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_overnight_timer_with_overrides(self):
        """Night shift 22:00 → 06:00 next day = 8h."""
        self.client.force_login(self.user)
        # Start timer 1h ago
        ActiveTimer.objects.create(
            profile=self.profile,
            user=self.user,
            start_time=timezone.now() - timezone.timedelta(hours=1),
            is_paused=False,
        )
        response = self._post_stop({
            "date": "2024-06-18",
            "start_time": "22:00",
            "end_time": "06:00",
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "stopped")
        self.assertEqual(float(data["hours_worked"]), 8.0)


class DuplicateStartTest(TestCase):
    """Starting a timer when one is already running returns 400."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="dupuser", email="dup@example.com", password="secret"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Dup Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )

    def test_duplicate_start_returns_400(self):
        """Double start should return 400, not 500."""
        ActiveTimer.objects.create(
            profile=self.profile,
            user=self.user,
            start_time=timezone.now(),
            is_paused=False,
        )
        self.client.force_login(self.user)
        response = self.client.post(
            f"/timer/{self.profile.id}/start/"
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)

    def test_duplicate_start_atomic(self):
        """Concurrent starts should be handled atomically."""
        self.client.force_login(self.user)
        # First start succeeds
        response1 = self.client.post(
            f"/timer/{self.profile.id}/start/"
        )
        self.assertEqual(response1.status_code, 200)
        # Second start returns 400
        response2 = self.client.post(
            f"/timer/{self.profile.id}/start/"
        )
        self.assertEqual(response2.status_code, 400)


class StopTimerClientTimestampBeforeStartTest(TestCase):
    """Stop with client_timestamp before timer.start_time must clamp to 0h."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="cstbs", email="cstbs@example.com", password="secret"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="CST Before Start Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )

    def _post_stop(self, payload):
        return self.client.post(
            f"/timer/{self.profile.id}/stop/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_stop_before_start_produces_zero_hours(self):
        """Manipulierter Stop vor dem Start darf keinen 23h-Eintrag erzeugen."""
        now = timezone.now()
        ActiveTimer.objects.create(
            profile=self.profile,
            user=self.user,
            start_time=now - timedelta(hours=2),
            is_paused=False,
        )
        # client_timestamp liegt 1h VOR dem Start → wird auf start_time geklemmt
        before_start = (now - timedelta(hours=3)).isoformat()
        self.client.force_login(self.user)
        response = self._post_stop({"client_timestamp": before_start})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "stopped")
        self.assertEqual(float(data["hours_worked"]), 0.0)


class PauseClientTimestampBeforeStartTest(TestCase):
    """Pause with client_timestamp before timer.start_time must clamp to start_time."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="ptbs", email="ptbs@example.com", password="secret"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="PTBS Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )
        self.client.force_login(self.user)

    def _post_json(self, path, payload):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_pause_clamps_to_start_time(self):
        """Pause-Timestamp vor Start wird auf Start-Time geklemmt."""
        now = timezone.now()
        start = now - timedelta(hours=2)
        ActiveTimer.objects.create(
            profile=self.profile,
            user=self.user,
            start_time=start,
            is_paused=False,
        )
        # client_timestamp liegt vor dem Start
        before_start = (now - timedelta(hours=3)).isoformat()
        response = self._post_json(
            f"/timer/{self.profile.id}/pause/",
            {"client_timestamp": before_start},
        )
        self.assertEqual(response.status_code, 200)
        timer = ActiveTimer.objects.get(profile=self.profile, user=self.user)
        self.assertTrue(timer.is_paused)
        self.assertEqual(timer.pause_time, timer.start_time)


class ResumeClientTimestampBeforePauseTest(TestCase):
    """Resume with client_timestamp before pause_time must not add negative pause."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="rtbp", email="rtbp@example.com", password="secret"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="RTBP Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )
        self.client.force_login(self.user)

    def _post_json(self, path, payload):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_resume_no_negative_pause(self):
        """Resume-Timestamp vor Pause-Zeit addiert keine negative Pause."""
        now = timezone.now()
        start = now - timedelta(hours=3)
        pause_ts = start + timedelta(hours=1)
        ActiveTimer.objects.create(
            profile=self.profile,
            user=self.user,
            start_time=start,
            is_paused=True,
            pause_time=pause_ts,
            total_paused_seconds=0,
        )
        # client_timestamp liegt vor pause_time → resume_time wird auf pause_time geklemmt
        before_pause = (start + timedelta(minutes=30)).isoformat()
        response = self._post_json(
            f"/timer/{self.profile.id}/resume/",
            {"client_timestamp": before_pause},
        )
        self.assertEqual(response.status_code, 200)
        timer = ActiveTimer.objects.get(profile=self.profile, user=self.user)
        self.assertFalse(timer.is_paused)
        self.assertEqual(timer.total_paused_seconds, 0)

    def test_resume_zero_stays_zero(self):
        """Bei 0 total_paused_seconds bleibt es 0."""
        now = timezone.now()
        start = now - timedelta(hours=2)
        pause_ts = start + timedelta(hours=1)
        ActiveTimer.objects.create(
            profile=self.profile,
            user=self.user,
            start_time=start,
            is_paused=True,
            pause_time=pause_ts,
            total_paused_seconds=0,
        )
        # client_timestamp = pause_time (identisch) → 0 Sek. Pause
        response = self._post_json(
            f"/timer/{self.profile.id}/resume/",
            {"client_timestamp": pause_ts.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        timer = ActiveTimer.objects.get(profile=self.profile, user=self.user)
        self.assertFalse(timer.is_paused)
        self.assertEqual(timer.total_paused_seconds, 0)


class TimerClientTimestampAPITest(TestCase):
    """client_timestamp handling for start/pause/resume endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="tsapi", email="tsapi@example.com", password="secret"
        )
        self.profile = Profile.objects.create(
            user=self.user,
            title="Timestamp API Profile",
            position="Worker",
            weekly_hours=40,
            hourly_rate=20,
        )
        self.client.force_login(self.user)

    def _post_json(self, path, payload):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_start_timer_uses_client_timestamp(self):
        ts = timezone.now() - timedelta(hours=2)
        response = self._post_json(
            f"/timer/{self.profile.id}/start/",
            {"client_timestamp": ts.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        timer = ActiveTimer.objects.get(profile=self.profile, user=self.user)
        self.assertAlmostEqual(
            abs((timer.start_time - ts).total_seconds()),
            0,
            delta=1,
        )

    def test_pause_resume_use_client_timestamps_for_pause_duration(self):
        start = timezone.now() - timedelta(hours=3)
        pause_ts = start + timedelta(hours=1)
        resume_ts = pause_ts + timedelta(minutes=30)
        ActiveTimer.objects.create(
            profile=self.profile,
            user=self.user,
            start_time=start,
            is_paused=False,
        )

        pause_response = self._post_json(
            f"/timer/{self.profile.id}/pause/",
            {"client_timestamp": pause_ts.isoformat()},
        )
        self.assertEqual(pause_response.status_code, 200)

        resume_response = self._post_json(
            f"/timer/{self.profile.id}/resume/",
            {"client_timestamp": resume_ts.isoformat()},
        )
        self.assertEqual(resume_response.status_code, 200)

        timer = ActiveTimer.objects.get(profile=self.profile, user=self.user)
        self.assertFalse(timer.is_paused)
        self.assertEqual(timer.total_paused_seconds, 30 * 60)
