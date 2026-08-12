from jobs.normalization import clean_text, detect_employment_type, detect_experience_level, detect_work_arrangement, parse_datetime

from .base import BaseJobSourceAdapter, ImportedJob, ImportPayloadError


def mapped_value(record, path, default=""):
    value = record
    for segment in str(path or "").split("."):
        if not segment:
            return default
        if isinstance(value, dict):
            value = value.get(segment, default)
        else:
            return default
    return value


class JSONFeedSourceAdapter(BaseJobSourceAdapter):
    required_mappings = ("external_job_id", "title", "description", "source_url")

    def fetch(self, limit=None):
        payload = self.fixture_data if self.fixture_data is not None else self.http_client.get_json(self.source.base_url)
        list_path = self.source.field_mapping.get("list_path", "")
        records = mapped_value(payload, list_path, payload) if list_path else payload
        if not isinstance(records, list):
            raise ImportPayloadError("Configured JSON feed list path does not resolve to a list.")
        return records[:limit] if limit else records

    def normalize(self, raw_record):
        mapping = self.source.field_mapping
        missing = [name for name in self.required_mappings if not mapping.get(name)]
        if missing:
            raise ImportPayloadError(f"JSON feed mapping is missing: {', '.join(missing)}")
        external_id = clean_text(mapped_value(raw_record, mapping["external_job_id"]))
        title = clean_text(mapped_value(raw_record, mapping["title"]))
        description = clean_text(mapped_value(raw_record, mapping["description"]))
        source_url = self.validated_url(mapped_value(raw_record, mapping["source_url"]), required=True)
        if not external_id or not title:
            raise ImportPayloadError("JSON feed record is missing its external ID or title.")
        location = clean_text(mapped_value(raw_record, mapping.get("location", "")))
        return ImportedJob(
            external_job_id=external_id, title=title, description=description,
            raw_source_text=description, source_url=source_url,
            application_url=self.validated_url(mapped_value(raw_record, mapping.get("application_url", ""))) or source_url,
            location=location,
            employment_type=detect_employment_type(title, description),
            work_arrangement=detect_work_arrangement(location, description),
            experience_level=detect_experience_level(title, description),
            posted_at=parse_datetime(mapped_value(raw_record, mapping.get("posted_at", ""))),
            expires_at=parse_datetime(mapped_value(raw_record, mapping.get("expires_at", ""))),
            salary_min=self.decimal_or_none(mapped_value(raw_record, mapping.get("salary_min", ""), None)),
            salary_max=self.decimal_or_none(mapped_value(raw_record, mapping.get("salary_max", ""), None)),
            salary_currency=clean_text(mapped_value(raw_record, mapping.get("salary_currency", ""))),
        )
