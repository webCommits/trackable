from django.db import models


class Holiday(models.Model):
    date = models.DateField()
    name = models.CharField(max_length=200)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="holidays",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["date"]
        verbose_name = "Holiday"
        verbose_name_plural = "Holidays"
        unique_together = [("date", "organization")]

    def __str__(self):
        return f"{self.date} – {self.name}"
