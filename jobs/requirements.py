import re
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ExtractedRequirements:
    minimum_gpa: Decimal | None = None
    exam_codes: tuple[str, ...] = ()
    skill_names: tuple[str, ...] = ()
    sponsorship_available: bool | None = None
    degree_requirement: str = ""
    years_experience: Decimal | None = None
    work_arrangement: str = ""


EXAMS = ("MAS-II", "MAS-I", "FAM", "SRM", "FM", "PA", "P")
SKILLS = ("Power BI", "Tableau", "Python", "Excel", "SQL", "SAS", "R")


def extract_requirements(text):
    text = re.sub(r"\s+", " ", text or "")
    lower = text.lower()
    gpa_match = re.search(r"(?:minimum|required|at least)\s+gpa(?:\s+of)?\s*[:]?\s*([0-4](?:\.\d{1,2})?)", lower)
    years_match = re.search(r"(?:minimum(?:\s+of)?|at least|required)\s+(\d+(?:\.\d+)?)\+?\s+years?", lower)
    if not years_match:
        years_match = re.search(r"(\d+(?:\.\d+)?)\+\s+years?", lower)
    exam_codes = tuple(
        code for code in EXAMS
        if re.search(
            rf"(?<![A-Za-z0-9-]){re.escape(code)}(?![A-Za-z0-9-]|&C\b)",
            text,
            re.I,
        )
    )
    skill_names = tuple(skill for skill in SKILLS if re.search(rf"(?<![A-Za-z0-9]){re.escape(skill)}(?![A-Za-z0-9])", text, re.I))
    sponsorship = None
    if re.search(r"(?:visa\s+)?sponsorship\s+(?:is\s+)?(?:available|provided)", lower):
        sponsorship = True
    elif re.search(r"(?:no|not)\s+(?:visa\s+)?sponsorship|unable to (?:provide|sponsor)|will not sponsor", lower):
        sponsorship = False
    degree = ""
    if re.search(r"doctor(?:ate|al)(?: degree)?(?: required)?|ph\.?d\.?", lower):
        degree = "doctorate"
    elif re.search(r"master'?s? degree(?: required)?", lower):
        degree = "master"
    elif re.search(r"bachelor[’']?s? degree(?: required)?", lower):
        degree = "bachelor"
    arrangement = "remote" if re.search(r"\bremote\b", lower) else "hybrid" if re.search(r"\bhybrid\b", lower) else "onsite" if re.search(r"\bon[- ]?site\b", lower) else ""
    return ExtractedRequirements(
        minimum_gpa=Decimal(gpa_match.group(1)) if gpa_match else None,
        exam_codes=exam_codes,
        skill_names=skill_names,
        sponsorship_available=sponsorship,
        degree_requirement=degree,
        years_experience=Decimal(years_match.group(1)) if years_match else None,
        work_arrangement=arrangement,
    )
