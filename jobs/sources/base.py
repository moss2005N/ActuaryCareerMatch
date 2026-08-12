from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


class ImportPayloadError(ValueError):
    """Raised when an authorized source returns unusable external data."""


@dataclass(frozen=True)
class ImportedJob:
    external_job_id: str
    title: str
    description: str
    source_url: str
    application_url: str = ""
    location: str = ""
    posted_at: datetime | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None


class BaseJobSourceAdapter(ABC):
    """Interface for one explicitly authorized job source.

    Concrete adapters must use official APIs or permitted public structured feeds,
    identify the application, enforce timeouts and source-specific rate limits, and
    stop on access restrictions. This interface intentionally provides no crawler.
    """

    request_timeout_seconds = 10
    minimum_request_interval_seconds = 1

    def __init__(self, source):
        self.source = source

    @abstractmethod
    def fetch(self):
        """Return an iterable of raw records from an authorized source."""

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

