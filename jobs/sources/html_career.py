from .base import BaseJobSourceAdapter


class HTMLCareerPageSource(BaseJobSourceAdapter):
    """Base for one approved company page with explicit parsing logic.

    This deliberately contains no generic link discovery or crawler. A concrete
    subclass must implement both fetch and normalize after a documented terms and
    robots review. CAPTCHA, login, anti-bot, or access blocks must stop collection.
    """

    pass
