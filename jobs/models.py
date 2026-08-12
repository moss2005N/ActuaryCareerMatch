from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from profiles.models import ActuarialExam, PracticeArea, Skill


class Company(models.Model):
    class Industry(models.TextChoices):
        INSURANCE = "insurance", "Insurance"
        CONSULTING = "consulting", "Consulting"
        REINSURANCE = "reinsurance", "Reinsurance"
        GOVERNMENT = "government", "Government"
        TECHNOLOGY = "technology", "Technology / InsurTech"
        OTHER = "other", "Other"

    class Size(models.TextChoices):
        SMALL = "1-50", "1–50"
        MEDIUM = "51-500", "51–500"
        LARGE = "501-5000", "501–5,000"
        ENTERPRISE = "5001+", "5,001+"

    name = models.CharField(max_length=200, unique=True)
    website = models.URLField(blank=True)
    careers_url = models.URLField(blank=True)
    description = models.TextField(blank=True)
    headquarters = models.CharField(max_length=200, blank=True)
    industry = models.CharField(max_length=30, choices=Industry.choices, blank=True)
    company_size = models.CharField(max_length=20, choices=Size.choices, blank=True)
    logo_url = models.URLField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(models.functions.Lower("name"), name="jobs_company_name_ci_unique")
        ]

    def __str__(self):
        return self.name


class JobSource(models.Model):
    class SourceType(models.TextChoices):
        MANUAL = "manual", "Manual entry"
        GREENHOUSE = "greenhouse", "Greenhouse public feed"
        LEVER = "lever", "Lever public feed"
        ATS_API = "ats_api", "Authorized ATS/API"
        CAREER_PAGE = "career_page", "Permitted career page"
        OTHER_API = "other_api", "Other authorized API"

    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pending review"
        ALLOWED = "allowed", "Reviewed and allowed"
        DISALLOWED = "disallowed", "Disallowed"
        NOT_APPLICABLE = "not_applicable", "Not applicable"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="job_sources", blank=True, null=True)
    name = models.CharField(max_length=100, unique=True)
    source_type = models.CharField(max_length=30, choices=SourceType.choices)
    base_url = models.URLField(blank=True)
    board_identifier = models.CharField(max_length=200, blank=True)
    field_mapping = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=False)
    request_timeout_seconds = models.PositiveSmallIntegerField(default=10, validators=[MinValueValidator(1), MaxValueValidator(60)])
    minimum_request_interval_seconds = models.DecimalField(max_digits=5, decimal_places=2, default=1, validators=[MinValueValidator(0)])
    missing_syncs_before_deactivation = models.PositiveSmallIntegerField(default=3, validators=[MinValueValidator(2)])
    robots_policy_status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    terms_review_status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    notes = models.TextField(blank=True)
    last_sync_at = models.DateTimeField(blank=True, null=True)
    last_success_at = models.DateTimeField(blank=True, null=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class JobPostingQuerySet(models.QuerySet):
    def visible(self):
        now = timezone.now()
        return self.filter(active=True, company__active=True).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )


class JobPosting(models.Model):
    class EmploymentType(models.TextChoices):
        INTERNSHIP = "internship", "Internship"
        FULL_TIME = "full_time", "Full-time"
        PART_TIME = "part_time", "Part-time"
        TEMPORARY = "temporary", "Temporary"

    class WorkArrangement(models.TextChoices):
        ONSITE = "onsite", "On-site"
        HYBRID = "hybrid", "Hybrid"
        REMOTE = "remote", "Remote"

    class ExperienceLevel(models.TextChoices):
        INTERNSHIP = "internship", "Internship"
        ENTRY = "entry", "Entry level"
        EXPERIENCED = "experienced", "Experienced"

    class SalaryPeriod(models.TextChoices):
        HOUR = "hour", "Per hour"
        YEAR = "year", "Per year"

    class DegreeRequirement(models.TextChoices):
        UNSPECIFIED = "unspecified", "Not specified"
        NONE = "none", "No degree requirement"
        BACHELOR = "bachelor", "Bachelor's degree"
        MASTER = "master", "Master's degree"
        DOCTORATE = "doctorate", "Doctorate"

    class Authorization(models.TextChoices):
        ANY = "any", "No restriction specified"
        AUTHORIZED = "authorized", "Must be authorized to work"
        US_CITIZEN = "us_citizen", "U.S. citizen required"
        PERMANENT_RESIDENT = "permanent_resident", "Permanent resident required"

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="jobs")
    source = models.ForeignKey(JobSource, on_delete=models.PROTECT, related_name="jobs", blank=True, null=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    location = models.CharField(max_length=200, blank=True)
    country = models.CharField(max_length=100, blank=True)
    state_or_region = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    employment_type = models.CharField(max_length=20, choices=EmploymentType.choices, blank=True)
    work_arrangement = models.CharField(max_length=20, choices=WorkArrangement.choices, blank=True)
    experience_level = models.CharField(max_length=20, choices=ExperienceLevel.choices, blank=True)
    salary_min = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0)])
    salary_max = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0)])
    salary_currency = models.CharField(max_length=3, default="USD")
    salary_period = models.CharField(max_length=10, choices=SalaryPeriod.choices, blank=True)
    application_url = models.URLField(blank=True)
    source_url = models.URLField(blank=True)
    source_name = models.CharField(max_length=100, blank=True)
    external_job_id = models.CharField(max_length=200, blank=True)
    posted_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    active = models.BooleanField(default=True)
    raw_source_text = models.TextField(blank=True)
    first_seen_at = models.DateTimeField(blank=True, null=True)
    last_seen_at = models.DateTimeField(blank=True, null=True)
    consecutive_missing_syncs = models.PositiveSmallIntegerField(default=0)
    practice_areas = models.ManyToManyField(PracticeArea, blank=True, related_name="job_postings")
    required_exams = models.ManyToManyField(ActuarialExam, blank=True, related_name="jobs_requiring_exam")
    preferred_exams = models.ManyToManyField(ActuarialExam, blank=True, related_name="jobs_preferring_exam")
    required_skills = models.ManyToManyField(Skill, blank=True, related_name="jobs_requiring_skill")
    preferred_skills = models.ManyToManyField(Skill, blank=True, related_name="jobs_preferring_skill")
    minimum_gpa = models.DecimalField(max_digits=3, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0), MaxValueValidator(4)])
    degree_requirement = models.CharField(max_length=20, choices=DegreeRequirement.choices, default=DegreeRequirement.UNSPECIFIED)
    major_requirements = models.TextField(blank=True, help_text="One acceptable major per line.")
    work_authorization_requirement = models.CharField(max_length=30, choices=Authorization.choices, default=Authorization.ANY)
    sponsorship_available = models.BooleanField(blank=True, null=True, default=None)
    years_experience = models.DecimalField(max_digits=4, decimal_places=1, blank=True, null=True, default=None, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = JobPostingQuerySet.as_manager()

    class Meta:
        ordering = ("-posted_at", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("source", "external_job_id"),
                condition=Q(source__isnull=False) & ~Q(external_job_id=""),
                name="jobs_source_external_id_unique",
            ),
            models.UniqueConstraint(
                fields=("company", "title", "location", "source_url"),
                condition=Q(external_job_id="") & ~Q(source_url=""),
                name="jobs_fallback_identity_unique",
            ),
        ]
        indexes = [
            models.Index(fields=("active", "expires_at")),
            models.Index(fields=("employment_type", "work_arrangement", "experience_level")),
        ]

    def clean(self):
        errors = {}
        if self.salary_min is not None and self.salary_max is not None and self.salary_max < self.salary_min:
            errors["salary_max"] = "Maximum salary cannot be lower than minimum salary."
        if self.source and self.source.source_type != JobSource.SourceType.MANUAL and not self.external_job_id and not self.source_url:
            errors["external_job_id"] = "Imported jobs require an external ID or source URL."
        if errors:
            raise ValidationError(errors)

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at <= timezone.now())

    def __str__(self):
        return f"{self.title} at {self.company}"


class ImportRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    source = models.ForeignKey(JobSource, on_delete=models.CASCADE, related_name="import_runs")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    jobs_seen = models.PositiveIntegerField(default=0)
    jobs_created = models.PositiveIntegerField(default=0)
    jobs_updated = models.PositiveIntegerField(default=0)
    jobs_skipped = models.PositiveIntegerField(default=0)
    jobs_deactivated = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    error_summary = models.TextField(blank=True)

    @property
    def records_seen(self):
        return self.jobs_seen

    @property
    def records_created(self):
        return self.jobs_created

    @property
    def records_updated(self):
        return self.jobs_updated

    class Meta:
        ordering = ("-started_at",)

    def __str__(self):
        return f"{self.source} — {self.get_status_display()} — {self.started_at:%Y-%m-%d %H:%M}"
