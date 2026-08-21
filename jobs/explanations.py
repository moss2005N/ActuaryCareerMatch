import hashlib
import json

from profiles.resume_analysis.base import ResumeAnalysisError
from profiles.resume_analysis.providers import get_provider

from .matching import profile_fingerprint
from .models import JobMatchExplanation

EXPLANATION_VERSION = "1"


def explanation_fingerprint(user, match):
    payload = {"profile": profile_fingerprint(user), "job": match.job_fingerprint, "match": match.explanation_json, "version": EXPLANATION_VERSION}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def get_cached_explanation(user, match):
    cached = JobMatchExplanation.objects.filter(match=match).first()
    if cached and cached.cache_fingerprint == explanation_fingerprint(user, match): return cached
    return None


def generate_explanation(user, match, provider=None, force=False):
    provider = provider or get_provider()
    fingerprint = explanation_fingerprint(user, match)
    cached = JobMatchExplanation.objects.filter(match=match).first()
    if cached and cached.cache_fingerprint == fingerprint and not force: return cached
    profile_data = {"degree_level": user.candidate_profile.degree_level, "major": user.candidate_profile.major, "gpa": str(user.candidate_profile.gpa) if user.candidate_profile.gpa is not None else None}
    job_data = {"title": match.job.title, "company": match.job.company.name}
    text = provider.generate_match_explanation(profile_data, job_data, match.explanation_json)
    if not isinstance(text, str) or not text.strip() or len(text) > 5000: raise ResumeAnalysisError("Provider returned an invalid match explanation.")
    explanation, _ = JobMatchExplanation.objects.update_or_create(match=match, defaults={"provider": provider.name, "provider_model": getattr(provider, "model", ""), "explanation_text": text.strip(), "cache_fingerprint": fingerprint, "explanation_version": EXPLANATION_VERSION})
    return explanation
