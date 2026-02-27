from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    email_notifications_enabled = models.BooleanField(default=True)
    password_reset_token = models.CharField(max_length=100, blank=True, null=True)
    password_reset_token_created = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.username
