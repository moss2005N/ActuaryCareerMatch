from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from jobs.matching import matching_queryset, recalculate_matches


class Command(BaseCommand):
    help = "Recalculate deterministic candidate-job matches."

    def add_arguments(self, parser):
        parser.add_argument("--user", type=int, help="Recalculate only this user ID.")
        parser.add_argument("--job", type=int, help="Recalculate only this job ID.")

    def handle(self, *args, **options):
        User = get_user_model()
        users = User.objects.filter(candidate_profile__isnull=False)
        jobs = matching_queryset()
        if options["user"]:
            users = users.filter(pk=options["user"])
            if not users.exists(): raise CommandError("User does not exist or has no candidate profile.")
        if options["job"]:
            jobs = jobs.filter(pk=options["job"])
            if not jobs.exists(): raise CommandError("Active job does not exist.")
        matches = recalculate_matches(users=users, jobs=jobs)
        self.stdout.write(self.style.SUCCESS(f"Recalculated {len(matches)} job match(es)."))
