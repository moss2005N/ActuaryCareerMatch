from jobs.normalization import clean_text, detect_employment_type, detect_experience_level, detect_work_arrangement, parse_datetime

from .base import BaseJobSourceAdapter, ImportedJob, ImportPayloadError


class LeverSourceAdapter(BaseJobSourceAdapter):
    def fetch(self, limit=None):
        if self.fixture_data is not None:
            payload = self.fixture_data
        else:
            if not self.source.board_identifier:
                raise ImportPayloadError("Lever source requires a site identifier.")
            url = f"https://api.lever.co/v0/postings/{self.source.board_identifier}?mode=json"
            payload = self.http_client.get_json(url)
        if not isinstance(payload, list):
            raise ImportPayloadError("Lever response is not a postings list.")
        return payload[:limit] if limit else payload

    def normalize(self, raw_record):
        try:
            external_id = str(raw_record["id"])
            title = clean_text(raw_record["text"])
        except (KeyError, TypeError) as exc:
            raise ImportPayloadError("Lever record is missing its ID or title.") from exc
        categories = raw_record.get("categories") or {}
        location = clean_text(categories.get("location", ""))
        description = clean_text(" ".join(filter(None, (
            raw_record.get("descriptionPlain"), raw_record.get("additionalPlain"),
            " ".join(item.get("content", "") for item in raw_record.get("lists", []) if isinstance(item, dict)),
        ))))
        source_url = self.validated_url(raw_record.get("hostedUrl"), required=True)
        application_url = self.validated_url(raw_record.get("applyUrl")) or source_url
        commitment = clean_text(categories.get("commitment", ""))
        return ImportedJob(
            external_job_id=external_id, title=title, description=description,
            raw_source_text=description, source_url=source_url, application_url=application_url,
            location=location,
            employment_type=detect_employment_type(title, f"{commitment} {description}"),
            work_arrangement=detect_work_arrangement(location, description),
            experience_level=detect_experience_level(title, description),
            posted_at=parse_datetime(raw_record.get("createdAt")),
        )
