from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


class Command(BaseCommand):
    help = "Create a fictional PDF resume for local mock-provider testing."

    def add_arguments(self, parser):
        parser.add_argument("output", nargs="?", default="/tmp/actuary-career-match-fictional-resume.pdf")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("The fictional resume fixture is available only when DEBUG=True.")
        source = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "fictional_resume.txt"
        text = source.read_text()
        writer = PdfWriter(); page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        safe = text.encode("ascii", "replace").decode().replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("\n", ") Tj 0 -14 Td (")
        stream = DecodedStreamObject(); stream.set_data(f"BT /F1 9 Tf 40 750 Td ({safe}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
        output = Path(options["output"]).expanduser().resolve()
        if output.suffix.lower() != ".pdf": raise CommandError("Output filename must end in .pdf")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("wb") as handle: writer.write(handle)
        self.stdout.write(self.style.SUCCESS(f"Created fictional resume fixture: {output}"))
