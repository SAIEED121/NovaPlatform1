from django.core.management.base import BaseCommand

from subscriptions.models import StudentSubscription


class Command(BaseCommand):
    help = "Automatically expire subscriptions past their end datetime."

    def handle(self, *args, **options):
        expired_count = StudentSubscription.objects.auto_expire()
        self.stdout.write(self.style.SUCCESS(f"Expired subscriptions updated: {expired_count}"))
