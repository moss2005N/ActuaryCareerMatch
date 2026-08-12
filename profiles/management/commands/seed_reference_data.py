from django.core.management.base import BaseCommand

from profiles.models import ActuarialExam, PracticeArea, Skill


EXAMS = {
    "SOA": [
        ("P", "Probability"), ("FM", "Financial Mathematics"),
        ("FAM", "Fundamentals of Actuarial Mathematics"),
        ("SRM", "Statistics for Risk Modeling"), ("PA", "Predictive Analytics"),
        ("ALTAM", "Advanced Long-Term Actuarial Mathematics"),
        ("ASTAM", "Advanced Short-Term Actuarial Mathematics"),
    ],
    "CAS": [
        ("MAS-I", "Modern Actuarial Statistics I"),
        ("MAS-II", "Modern Actuarial Statistics II"),
        ("Exam 5", "Basic Techniques for Ratemaking and Estimating Claim Liabilities"),
        ("Exam 6", "Regulation and Financial Reporting"),
        ("Exam 7", "Advanced Estimation of Claims Liabilities"),
        ("Exam 8", "Advanced Ratemaking"),
        ("Exam 9", "Financial Risk and Rate of Return"),
    ],
}

SKILLS = [
    ("Excel", "office"), ("VBA", "programming"), ("Python", "programming"),
    ("R", "programming"), ("SQL", "data"), ("SAS", "data"),
    ("Tableau", "visualization"), ("Power BI", "visualization"),
    ("Prophet", "actuarial"), ("Git", "programming"),
    ("Financial Modeling", "modeling"), ("Actuarial Modeling", "actuarial"),
    ("Data Analysis", "data"), ("Machine Learning", "data"),
]

PRACTICE_AREAS = [
    "Life", "Health", "Property & Casualty", "Pension / Retirement",
    "Actuarial Consulting", "Reinsurance", "Enterprise Risk Management",
    "Employee Benefits", "Government", "InsurTech",
]


class Command(BaseCommand):
    help = "Create or update actuarial exams, skills, and practice areas."

    def handle(self, *args, **options):
        for organization, exams in EXAMS.items():
            for order, (code, name) in enumerate(exams, 1):
                ActuarialExam.objects.update_or_create(
                    organization=organization,
                    code=code,
                    defaults={"name": name, "active": True, "display_order": order},
                )
        for name, category in SKILLS:
            Skill.objects.update_or_create(name=name, defaults={"category": category, "active": True})
        for order, name in enumerate(PRACTICE_AREAS, 1):
            PracticeArea.objects.update_or_create(
                name=name,
                defaults={"active": True, "display_order": order},
            )
        self.stdout.write(self.style.SUCCESS("Reference data seeded successfully."))
