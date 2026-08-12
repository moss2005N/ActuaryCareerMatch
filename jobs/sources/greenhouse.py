from jobs.normalization import clean_text, detect_employment_type, detect_experience_level, detect_work_arrangement

from .base import BaseJobSourceAdapter, ImportedJob, ImportPayloadError


class GreenhouseSourceAdapter(BaseJobSourceAdapter):
    def fetch(self, limit=None):
        if self.fixture_data is not None:
            payload = self.fixture_data
        else:
            if not self.source.board_identifier:
                raise ImportPayloadError("Greenhouse source requires a board identifier.")
            url = f"https://boards-api.greenhouse.io/v1/boards/{self.source.board_identifier}/jobs?content=true"
            payload = self.http_client.get_json(url)
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise ImportPayloadError("Greenhouse response does not contain a jobs list.")
        return jobs[:limit] if limit else jobs

    def normalize(self, raw_record):
        try:
            external_id = str(raw_record["id"])
            title = clean_text(raw_record["title"])
        except (KeyError, TypeError) as exc:
            raise ImportPayloadError("Greenhouse record is missing its ID or title.") from exc
        description = clean_text(raw_record.get("content", ""))
        location = clean_text((raw_record.get("location") or {}).get("name", ""))
        source_url = self.validated_url(raw_record.get("absolute_url"), required=True)
        return ImportedJob(
            external_job_id=external_id,
            title=title,
            description=description,
            raw_source_text=description,
            source_url=source_url,
            application_url=source_url,
            location=location,
            employment_type=detect_employment_type(title, description),
            work_arrangement=detect_work_arrangement(location, description),
            experience_level=detect_experience_level(title, description),
            # Greenhouse exposes an update timestamp here, not a publication
            # timestamp. Leave posted_at unknown rather than mislabeling it.
            posted_at=None,
        )
