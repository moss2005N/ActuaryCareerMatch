import re

ACTUARIAL_PATTERN = re.compile(
    r"\b(actuary|actuaries|actuarial(?:\s+(?:analyst|intern|consultant|associate))?|pricing\s+actuary|reserving\s+actuary)\b",
    re.IGNORECASE,
)


def is_actuarial_relevant(title, description=""):
    return bool(ACTUARIAL_PATTERN.search(f"{title} {description}"))
