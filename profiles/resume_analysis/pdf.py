from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .base import ResumeAnalysisError


def extract_pdf_text(file_object, *, max_pages=10, max_characters=50000):
    try:
        file_object.seek(0)
        reader = PdfReader(file_object, strict=True)
        if reader.is_encrypted:
            raise ResumeAnalysisError("Password-protected resumes cannot be analyzed.")
        if len(reader.pages) > max_pages:
            raise ResumeAnalysisError(f"Resume exceeds the {max_pages}-page analysis limit.")
        chunks = []
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
            if sum(len(chunk) for chunk in chunks) > max_characters:
                raise ResumeAnalysisError("Resume text exceeds the analysis character limit.")
    except (PdfReadError, EOFError, ValueError, TypeError, OSError) as exc:
        raise ResumeAnalysisError("The PDF is corrupted or unreadable.") from exc
    text = "\n".join(chunks).strip()
    if not text:
        raise ResumeAnalysisError("No readable text was found. Image-only resumes are not supported.")
    return text
