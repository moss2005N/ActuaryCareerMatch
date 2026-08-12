import json
import logging
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

logger = logging.getLogger("jobs.imports")


@dataclass
class HTTPClientError(Exception):
    message: str
    status_code: int | None = None
    retryable: bool = False
    blocked: bool = False

    def __str__(self):
        return self.message


class SourceHTTPClient:
    user_agent = "ActuaryCareerMatch-JobImporter/1.0 (+contact: admin@localhost)"
    retry_statuses = {429, 500, 502, 503, 504}
    no_retry_statuses = {401, 403, 404}

    def __init__(self, source, *, opener=None, sleep=None, monotonic=None, max_retries=2):
        self.source = source
        self.opener = opener or build_opener()
        self.sleep = sleep or time.sleep
        self.monotonic = monotonic or time.monotonic
        self.max_retries = max_retries
        self._last_request_at = None

    def _pace(self):
        if self._last_request_at is None:
            return
        elapsed = self.monotonic() - self._last_request_at
        wait = float(self.source.minimum_request_interval_seconds) - elapsed
        if wait > 0:
            self.sleep(wait)

    def get_json(self, url):
        body = self.get(url)
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPClientError("Source returned malformed JSON.") from exc

    def get(self, url):
        for attempt in range(self.max_retries + 1):
            self._pace()
            request = Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json, text/html;q=0.8"})
            try:
                response = self.opener.open(request, timeout=self.source.request_timeout_seconds)
                self._last_request_at = self.monotonic()
                body = response.read()
                preview = body[:20_000].decode("utf-8", errors="ignore").lower()
                if any(marker in preview for marker in ("captcha", "verify you are human", "access denied")):
                    raise HTTPClientError("Source returned a CAPTCHA or explicit access block.", blocked=True)
                return body
            except HTTPError as exc:
                self._last_request_at = self.monotonic()
                if exc.code in self.no_retry_statuses:
                    raise HTTPClientError(f"Source access stopped with HTTP {exc.code}.", exc.code, blocked=exc.code in {401, 403}) from exc
                retryable = exc.code in self.retry_statuses
                if not retryable or attempt >= self.max_retries:
                    raise HTTPClientError(f"Source request failed with HTTP {exc.code}.", exc.code, retryable=retryable) from exc
            except (TimeoutError, URLError) as exc:
                self._last_request_at = self.monotonic()
                if attempt >= self.max_retries:
                    raise HTTPClientError("Source request timed out or was unavailable.", retryable=True) from exc
            self.sleep(2 ** attempt)
        raise HTTPClientError("Source request failed.")
