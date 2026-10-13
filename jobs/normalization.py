import html
import re
from datetime import datetime, timezone
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def clean_text(value):
    parser = _TextExtractor()
    parser.feed(html.unescape(str(value or "")))
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def parse_datetime(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(text)
    except ValueError:
        return None
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def detect_employment_type(title, text):
    haystack = f"{title} {text}".lower()
    if re.search(r"\bintern(ship)?\b", haystack):
        return "internship"
    if "part-time" in haystack or "part time" in haystack:
        return "part_time"
    if "temporary" in haystack or "contract position" in haystack:
        return "temporary"
    if "full-time" in haystack or "full time" in haystack:
        return "full_time"
    return ""


def detect_work_arrangement(location, text):
    haystack = f"{location} {text}".lower()
    if re.search(r"\bremote\b", haystack):
        return "remote"
    if re.search(r"\bhybrid\b", haystack):
        return "hybrid"
    if "on-site" in haystack or "onsite" in haystack:
        return "onsite"
    return ""


def detect_experience_level(title, text):
    haystack = f"{title} {text}".lower()
    if re.search(r"\bintern(ship)?\b", haystack):
        return "internship"
    if re.search(r"\b(entry[- ]level|new grad(uate)?|junior)\b", haystack):
        return "entry"
    if re.search(r"\b(senior|experienced|manager|director|fellow)\b", haystack):
        return "experienced"
    return ""
