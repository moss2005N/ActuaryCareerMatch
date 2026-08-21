import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateResumeStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.PRIVATE_MEDIA_ROOT, base_url="/private-media/")


private_resume_storage = PrivateResumeStorage()


def resume_upload_path(instance, filename):
    return f"resumes/{instance.user_id}/{uuid.uuid4().hex}.pdf"


def validate_resume_file(upload):
    if upload.size > 5 * 1024 * 1024:
        raise ValidationError("Resume files must be 5 MB or smaller.")
    content_type = getattr(upload, "content_type", None)
    if content_type and content_type != "application/pdf":
        raise ValidationError("Resume files must use the PDF MIME type.")
    position = upload.tell()
    signature = upload.read(5)
    upload.seek(position)
    if signature != b"%PDF-":
        raise ValidationError("The uploaded file is not a valid PDF.")


class PracticeArea(models.Model):
    name = models.CharField(max_length=100, unique=True)
    active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("display_order", "name")

    def __str__(self):
        return self.name


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

    class DegreeLevel(models.TextChoices):
        HIGH_SCHOOL = "high_school", "High school"
        ASSOCIATE = "associate", "Associate"
        BACHELOR = "bachelor", "Bachelor's"
        MASTER = "master", "Master's"
        DOCTORATE = "doctorate", "Doctorate"
        OTHER = "other", "Other"

    class JobLevel(models.TextChoices):
        INTERNSHIP = "internship", "Internship"
        ENTRY = "entry", "Entry level"
        ASSOCIATE = "associate", "Associate"
        MID = "mid", "Mid level"
        SENIOR = "senior", "Senior"

    class Currency(models.TextChoices):
        USD = "USD", "USD"
        CAD = "CAD", "CAD"
        GBP = "GBP", "GBP"
        EUR = "EUR", "EUR"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="candidate_profile",
    )
    full_name = models.CharField(max_length=150, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state_or_region = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    preferred_locations = models.TextField(blank=True, help_text="One location per line.")
    university = models.CharField(max_length=200, blank=True)
    degree_level = models.CharField(max_length=20, choices=DegreeLevel.choices, blank=True)
    major = models.CharField(max_length=150, blank=True)
    minor = models.CharField(max_length=150, blank=True)
    gpa = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(0), MaxValueValidator(4)],
    )
    expected_graduation_date = models.DateField(blank=True, null=True)
    preferred_employment_type = models.CharField(max_length=20, choices=EmploymentType.choices, blank=True)
    preferred_work_arrangement = models.CharField(max_length=20, choices=WorkArrangement.choices, blank=True)
    requires_visa_sponsorship = models.BooleanField(default=False)
    employment_authorization_status = models.CharField(max_length=150, blank=True)
    linkedin_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    preferred_practice_areas = models.ManyToManyField(PracticeArea, blank=True, related_name="candidate_profiles")
    willing_to_relocate = models.BooleanField(default=False)
    target_job_level = models.CharField(max_length=20, choices=JobLevel.choices, blank=True)
    preferred_salary_minimum = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0)])
    preferred_salary_currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD, blank=True)
    resume = models.FileField(
        upload_to=resume_upload_path,
        storage=private_resume_storage,
        validators=[FileExtensionValidator(["pdf"]), validate_resume_file],
        blank=True,
    )
    resume_original_filename = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def resume_filename(self):
        return self.resume_original_filename or (Path(self.resume.name).name if self.resume else "")

    def __str__(self):
        return self.full_name or self.user.get_username()


class ActuarialExam(models.Model):
    class Organization(models.TextChoices):
        SOA = "SOA", "SOA"
        CAS = "CAS", "CAS"

    organization = models.CharField(max_length=3, choices=Organization.choices)
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("organization", "display_order", "code")
        constraints = [models.UniqueConstraint(fields=("organization", "code"), name="profiles_exam_org_code_unique")]

    def __str__(self):
        return f"{self.organization} {self.code} — {self.name}"


class UserExam(models.Model):
    class Status(models.TextChoices):
        PASSED = "passed", "Passed"
        STUDYING = "studying", "Studying"
        REGISTERED = "registered", "Registered"
        PLANNED = "planned", "Planned"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exams")
    exam = models.ForeignKey(ActuarialExam, on_delete=models.PROTECT, related_name="user_exams")
    status = models.CharField(max_length=12, choices=Status.choices)
    passed_date = models.DateField(blank=True, null=True)
    planned_exam_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("exam__organization", "exam__display_order")
        constraints = [models.UniqueConstraint(fields=("user", "exam"), name="profiles_user_exam_unique")]

    def clean(self):
        if self.status == self.Status.PASSED and self.planned_exam_date:
            raise ValidationError({"planned_exam_date": "Passed exams cannot have a planned exam date."})
        if self.status != self.Status.PASSED and self.passed_date:
            raise ValidationError({"passed_date": "Only passed exams can have a passed date."})

    def __str__(self):
        return f"{self.user}: {self.exam} ({self.get_status_display()})"


class Skill(models.Model):
    class Category(models.TextChoices):
        PROGRAMMING = "programming", "Programming"
        DATA = "data", "Data"
        ACTUARIAL = "actuarial", "Actuarial"
        VISUALIZATION = "visualization", "Visualization"
        OFFICE = "office", "Office"
        MODELING = "modeling", "Modeling"
        OTHER = "other", "Other"

    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ("category", "name")

    def __str__(self):
        return self.name


class UserSkill(models.Model):
    class Proficiency(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"
        EXPERT = "expert", "Expert"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="skills")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT, related_name="user_skills")
    proficiency_level = models.CharField(max_length=20, choices=Proficiency.choices)
    years_experience = models.DecimalField(max_digits=4, decimal_places=1, default=0, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ("skill__category", "skill__name")
        constraints = [models.UniqueConstraint(fields=("user", "skill"), name="profiles_user_skill_unique")]

    def __str__(self):
        return f"{self.user}: {self.skill}"


class Education(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="education_history")
    institution = models.CharField(max_length=200)
    degree = models.CharField(max_length=150)
    major = models.CharField(max_length=150)
    minor = models.CharField(max_length=150, blank=True)
    gpa = models.DecimalField(max_digits=3, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0), MaxValueValidator(4)])
    start_date = models.DateField(blank=True, null=True)
    graduation_date = models.DateField(blank=True, null=True)
    current = models.BooleanField(default=False)

    class Meta:
        ordering = ("-current", "-graduation_date", "institution")

    def clean(self):
        if self.start_date and self.graduation_date and self.graduation_date < self.start_date:
            raise ValidationError({"graduation_date": "Graduation date cannot be earlier than start date."})

    def __str__(self):
        return f"{self.institution} — {self.degree}"


class WorkExperience(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="work_experiences")
    company = models.CharField(max_length=200)
    job_title = models.CharField(max_length=150)
    location = models.CharField(max_length=150, blank=True)
    employment_type = models.CharField(max_length=20, choices=CandidateProfile.EmploymentType.choices, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    currently_working = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("-currently_working", "-start_date")

    def clean(self):
        errors = {}
        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "End date cannot be earlier than start date."
        if self.currently_working and self.end_date:
            errors["end_date"] = "End date must be empty for current positions."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.job_title} at {self.company}"


class ResumeAnalysis(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="resume_analyses")
    resume_identifier = models.CharField(max_length=64)
    provider = models.CharField(max_length=50)
    provider_model = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    extracted_data = models.JSONField(default=dict, blank=True)
    suggestions = models.JSONField(default=list, blank=True)
    feedback = models.JSONField(default=list, blank=True)
    analysis_version = models.CharField(max_length=20, default="1")
    error_message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("user", "resume_identifier", "status"))]

    def __str__(self):
        return f"{self.user} — {self.get_status_display()} — {self.created_at:%Y-%m-%d}"


class ResumeSuggestion(models.Model):
    class Kind(models.TextChoices):
        PROFILE = "profile", "Profile"
        EXAM = "exam", "Actuarial exam"
        SKILL = "skill", "Skill"
        EDUCATION = "education", "Education"
        EXPERIENCE = "experience", "Work experience"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        IGNORED = "ignored", "Ignored"

    analysis = models.ForeignKey(ResumeAnalysis, on_delete=models.CASCADE, related_name="review_items")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    fingerprint = models.CharField(max_length=64)
    label = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    confidence = models.CharField(max_length=12, choices=(("high", "High"), ("medium", "Medium"), ("low", "Low")))
    source_snippet = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    reviewed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("pk",)
        constraints = [models.UniqueConstraint(fields=("analysis", "fingerprint"), name="profiles_resume_suggestion_unique")]

    def __str__(self):
        return self.label
