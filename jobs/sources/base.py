from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


class ImportPayloadError(ValueError):
    """An authorized source returned a malformed or unusable record."""


@dataclass(frozen=True)
class ImportedJob:
    external_job_id: str
    title: str
    description: str
    source_url: str
    application_url: str = ""
    location: str = ""
    city: str = ""
    state_or_region: str = ""
    country: str = ""
    employment_type: str = ""
    work_arrangement: str = ""
    experience_level: str = ""
    posted_at: datetime | None = None
    expires_at: datetime | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_currency: str = ""
    salary_period: str = ""
    raw_source_text: str = ""
    explicitly_closed: bool = False
    metadata: dict = field(default_factory=dict)


class BaseJobSourceAdapter(ABC):
    """One adapter for one explicitly reviewed public or authorized source."""

    def __init__(self, source, http_client=None, fixture_data=None):
        self.source = source
        self.http_client = http_client
        self.fixture_data = fixture_data

    @abstractmethod
    def fetch(self, limit=None):
        """Return raw source records. Never bypass access restrictions."""

    @abstractmethod
    def normalize(self, raw_record) -> ImportedJob:
        """Validate and normalize one source-specific record."""

    @staticmethod
    def validated_url(value, *, required=False):
        value = (value or "").strip()
        if not value and not required:
            return ""
        try:
            URLValidator(schemes=("http", "https"))(value)
        except ValidationError as exc:
            raise ImportPayloadError("External record contains an invalid URL.") from exc
        if urlparse(value).scheme not in ("http", "https"):
            raise ImportPayloadError("Only HTTP(S) external URLs are accepted.")
        return value

    @staticmethod
    def decimal_or_none(value):
        if value in (None, ""):
            return None
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ImportPayloadError("External record contains an invalid numeric value.") from exc
        if result < 0:
            raise ImportPayloadError("External numeric values cannot be negative.")
        return result
