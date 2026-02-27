from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from trackable.profiles.models import Profile

User = get_user_model()


class ProfileModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_create_profile(self):
        profile = Profile.objects.create(
            user=self.user,
            title="Software Developer",
            position="Senior Developer",
            address="Berlin, Germany",
            weekly_hours=40,
            hourly_rate=75.50,
        )

        self.assertEqual(profile.user, self.user)
        self.assertEqual(profile.title, "Software Developer")
        self.assertEqual(profile.weekly_hours, 40)
        self.assertEqual(profile.hourly_rate, 75.50)

    def test_profile_str(self):
        profile = Profile.objects.create(
            user=self.user,
            title="Software Developer",
            position="Senior Developer",
            weekly_hours=40,
            hourly_rate=75.50,
        )

        self.assertEqual(str(profile), "Software Developer - Senior Developer")


class ProfileViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")

    def test_profile_create(self):
        response = self.client.post(
            reverse("profile_create"),
            {
                "title": "Software Developer",
                "position": "Senior Developer",
                "address": "Berlin, Germany",
                "weekly_hours": 40,
                "hourly_rate": 75.50,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Profile.objects.filter(user=self.user).exists())

    def test_profile_list(self):
        Profile.objects.create(
            user=self.user,
            title="Job 1",
            position="Position 1",
            weekly_hours=40,
            hourly_rate=50,
        )

        response = self.client.get(reverse("profile_list"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Job 1")

    def test_profile_detail(self):
        profile = Profile.objects.create(
            user=self.user,
            title="Software Developer",
            position="Senior Developer",
            weekly_hours=40,
            hourly_rate=75.50,
        )

        response = self.client.get(reverse("profile_detail", kwargs={"pk": profile.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Software Developer")
