import re

from django.conf import settings

from .base import ProviderUnavailableError, ResumeAnalysisProvider


class MockResumeAnalysisProvider(ResumeAnalysisProvider):
    name = "mock"
    model = "deterministic-resume-v1"

    def analyze_resume(self, text):
        # The resume is data only. Prompt-like phrases receive no special handling.
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        output = {key: [] for key in ("contact", "education", "experience", "skills", "exams", "credentials", "projects", "leadership", "languages", "feedback")}
        if lines and re.fullmatch(r"[A-Za-z][A-Za-z .'-]{2,100}", lines[0]):
            output["contact"].append({"name": "full_name", "value": lines[0], "confidence": "medium", "source_snippet": lines[0]})
        email = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
        if email: output["contact"].append({"name": "email", "value": email.group(0), "confidence": "high", "source_snippet": email.group(0)})
        phone = re.search(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)", text)
        if phone: output["contact"].append({"name": "phone", "value": phone.group(0), "confidence": "high", "source_snippet": phone.group(0)})
        for skill in ("Excel", "VBA", "Python", "R", "SQL", "SAS", "Tableau", "Power BI", "Prophet"):
            match = re.search(rf"(?<![A-Za-z]){re.escape(skill)}(?![A-Za-z])", text, re.I)
            if match: output["skills"].append({"name": skill, "confidence": "high", "source_snippet": match.group(0)})
        for exam in ("MAS-II", "MAS-I", "ALTAM", "ASTAM", "FAM", "SRM", "FM", "PA", "P"):
            match = re.search(rf"\bExam\s+{re.escape(exam)}\s*[^A-Za-z0-9\n]{{0,8}}\s*(Passed|Registered|Studying|Planned)\b", text, re.I)
            if match: output["exams"].append({"name": exam, "status": match.group(1).lower(), "confidence": "high", "source_snippet": match.group(0)})
        for credential in ("ASA", "FSA", "ACAS", "FCAS"):
            match = re.search(rf"\b{credential}\b", text)
            if match: output["credentials"].append({"name": credential, "confidence": "medium", "source_snippet": match.group(0)})
        gpa = re.search(r"\bGPA\s*[:=]?\s*([0-4](?:\.\d{1,2})?)\b", text, re.I)
        if gpa: output["education"].append({"gpa": gpa.group(1), "confidence": "high", "source_snippet": gpa.group(0)})
        education = re.search(r"(?im)^(?P<institution>[^\n]{2,100}(?:University|College))\s*[|,—-]\s*(?P<degree>BS|BA|Bachelor(?:'s)?|MS|Master(?:'s)?)\s+(?:in\s+)?(?P<major>[^\n,;]{2,80})", text)
        if education: output["education"].append({**education.groupdict(), "confidence": "medium", "source_snippet": education.group(0)[:500]})
        experience = re.search(r"(?im)^(?P<company>[^\n|]{2,100})\s*\|\s*(?P<job_title>[^\n|]{2,100})\s*\|\s*(?P<start>\d{4}-\d{2}-\d{2})\s+to\s+(?P<end>\d{4}-\d{2}-\d{2}|Present)$", text)
        if experience:
            values = experience.groupdict(); end = values.pop("end"); values["start_date"] = values.pop("start"); values["end_date"] = None if end.lower() == "present" else end; values["current"] = end.lower() == "present"
            output["experience"].append({**values, "confidence": "high", "source_snippet": experience.group(0)[:500]})
        output["feedback"] = self._feedback(text, output)
        return output

    def _feedback(self, text, output):
        feedback = []
        if not re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text): feedback.append({"category": "contact", "message": "Consider including a clear professional email address.", "confidence": "high", "source_snippet": ""})
        if not output["exams"]: feedback.append({"category": "actuarial exams", "message": "Make actuarial exam progress explicit, including status.", "confidence": "medium", "source_snippet": ""})
        if not re.search(r"\b\d+(?:%|\+|\s+(?:hours|days|clients|reports))\b", text, re.I): feedback.append({"category": "measurable impact", "message": "Add measurable outcomes where accurate and relevant.", "confidence": "medium", "source_snippet": ""})
        if len(text) > 12000: feedback.append({"category": "length", "message": "Review whether the resume can be made more concise.", "confidence": "medium", "source_snippet": ""})
        return feedback

    def generate_match_explanation(self, profile_data, job_data, match_result):
        strengths = match_result.get("matched_items", [])[:3]
        gaps = (match_result.get("missing_items", []) + match_result.get("warnings", []))[:2]
        lead = f"This {match_result.get('overall_score')}% match reflects the structured profile and explicit requirements for {job_data.get('title', 'this role')}."
        if strengths: lead += " Key alignment: " + " ".join(strengths)
        if gaps: lead += " Important gaps or uncertainties: " + " ".join(gaps)
        return lead


class UnavailableResumeAnalysisProvider(ResumeAnalysisProvider):
    name = "unavailable"

    def analyze_resume(self, text): raise ProviderUnavailableError("The configured AI resume provider is unavailable.")
    def generate_match_explanation(self, profile_data, job_data, match_result): raise ProviderUnavailableError("Enhanced explanations are unavailable.")


def get_provider():
    if settings.AI_RESUME_PROVIDER == "mock": return MockResumeAnalysisProvider()
    return UnavailableResumeAnalysisProvider()
