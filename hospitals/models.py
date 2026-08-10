"""Hospital tenant model — includes Ward and Bed sub-entities."""

from django.db import models

from core.models import TimeStampedModel


class Hospital(TimeStampedModel):
    """
    Represents a participating hospital/clinic.

    Each hospital is a tenant in the single central database.
    Staff members (User) belong to a hospital; patients and their records
    exist at the central level and are NOT restricted to a single hospital.
    """

    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(
        max_length=10,
        unique=True,
        help_text="Short uppercase code, e.g. UGMC, KATH, TRUST.",
    )
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="Ghana")
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Hospital"
        verbose_name_plural = "Hospitals"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Ward(TimeStampedModel):
    """A ward (department) within a hospital — contains beds."""

    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="wards")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, help_text="Short identifier, e.g. W3A, ICU, PEDS")
    capacity = models.PositiveIntegerField(default=0, help_text="Max bed count")

    class Meta:
        unique_together = ("hospital", "code")
        ordering = ["hospital", "name"]
        verbose_name = "Ward"

    def __str__(self):
        return f"{self.hospital.code} › {self.code}: {self.name}"

    @property
    def occupied_count(self):
        return self.beds.filter(status=Bed.Status.OCCUPIED).count()

    @property
    def available_count(self):
        return self.beds.filter(status=Bed.Status.AVAILABLE).count()


class Bed(TimeStampedModel):
    """A single bed within a ward."""

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        OCCUPIED = "occupied", "Occupied"
        CLEANING = "cleaning", "Being Cleaned"
        MAINTENANCE = "maintenance", "Under Maintenance"

    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="beds")
    label = models.CharField(max_length=20, help_text="Bed identifier, e.g. A1, B3")
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.AVAILABLE)
    current_patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_bed",
    )

    class Meta:
        unique_together = ("ward", "label")
        ordering = ["ward", "label"]
        verbose_name = "Bed"

    def __str__(self):
        return f"Bed {self.label} — {self.ward.code} ({self.get_status_display()})"
