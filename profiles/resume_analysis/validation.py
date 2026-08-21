import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .base import MalformedProviderOutputError

ALLOWED_KEYS = {"contact", "education", "experience", "skills", "exams", "credentials", "projects", "leadership", "languages", "feedback"}
CONFIDENCE = {"high", "medium", "low"}
EXAMS = {"P", "FM", "FAM", "SRM", "PA", "ALTAM", "ASTAM", "MAS-I", "MAS-II"}
CREDENTIALS = {"ASA", "FSA", "ACAS", "FCAS"}
SKILLS = {"Excel", "VBA", "Python", "R", "SQL", "SAS", "Tableau", "Power BI", "Prophet"}


def safe_date(value):
    if not value: return None
    try: return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError): return None


def validate_analysis_output(data):
    if not isinstance(data, dict) or not set(data).issubset(ALLOWED_KEYS):
        raise MalformedProviderOutputError("Provider returned an invalid analysis object.")
    result = {key: [] for key in ALLOWED_KEYS}
    for key in ALLOWED_KEYS:
        value = data.get(key, [])
        if not isinstance(value, list): raise MalformedProviderOutputError(f"Provider field {key} must be a list.")
        for item in value[:100]:
            if not isinstance(item, dict): raise MalformedProviderOutputError(f"Provider field {key} contains an invalid item.")
            confidence = item.get("confidence", "low")
            snippet = str(item.get("source_snippet", ""))[:500]
            if confidence not in CONFIDENCE: raise MalformedProviderOutputError("Provider returned an invalid confidence value.")
            clean = {k: v for k, v in item.items() if k in {"value", "name", "status", "institution", "degree", "major", "gpa", "graduation_date", "company", "job_title", "start_date", "end_date", "current", "description", "category", "message"}}
            clean.update(confidence=confidence, source_snippet=snippet)
            if key == "exams" and str(clean.get("name", "")).upper() not in EXAMS: continue
            if key == "exams" and clean.get("status") not in {"passed", "registered", "studying", "planned"}: continue
            if key == "credentials" and str(clean.get("name", "")).upper() not in CREDENTIALS: continue
            if key == "skills" and str(clean.get("name", "")) not in SKILLS: continue
            if "gpa" in clean:
                try:
                    gpa = Decimal(str(clean["gpa"])); clean["gpa"] = str(gpa) if Decimal("0") <= gpa <= Decimal("4") else None
                except (InvalidOperation, TypeError): clean["gpa"] = None
            for field in ("graduation_date", "start_date", "end_date"):
                if field in clean: clean[field] = safe_date(clean[field])
            result[key].append(clean)
    return result
