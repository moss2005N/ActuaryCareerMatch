from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class CandidateProfile(models.Model):
    class EmploymentType(models.TextChoices):
        INTERNSHIP = "internship", "Internship"
        FULL_TIME = "full_time", "Full time"
        PART_TIME = "part_time", "Part time"
        CONTRACT = "contract", "Contract"

    class WorkArrangement(models.TextChoices):
        ONSITE = "onsite", "On-site"
        HYBRID = "hybrid", "Hybrid"
        REMOTE = "remote", "Remote"
        FLEXIBLE = "flexible", "Flexible"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="candidate_profile",
    )
    full_name = models.CharField(max_length=150, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    university = models.CharField(max_length=200, blank=True)
    major = models.CharField(max_length=150, blank=True)
    gpa = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(0), MaxValueValidator(4)],
    )
    expected_graduation_date = models.DateField(blank=True, null=True)
    preferred_employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        blank=True,
    )
    preferred_work_arrangement = models.CharField(
        max_length=20,
        choices=WorkArrangement.choices,
        blank=True,
    )
    requires_visa_sponsorship = models.BooleanField(default=False)
    employment_authorization_status = models.CharField(max_length=150, blank=True)
    linkedin_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name or self.user.get_username()

