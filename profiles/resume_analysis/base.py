from abc import ABC, abstractmethod


class ResumeAnalysisError(Exception):
    pass


class ProviderUnavailableError(ResumeAnalysisError):
    pass


class MalformedProviderOutputError(ResumeAnalysisError):
    pass


class ResumeAnalysisProvider(ABC):
    name = "base"
    model = ""

    @abstractmethod
    def analyze_resume(self, text):
        """Return validated-candidate structured data; resume text is untrusted data."""

    @abstractmethod
    def generate_match_explanation(self, profile_data, job_data, match_result):
        """Explain existing deterministic results without modifying them."""
