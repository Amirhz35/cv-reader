from django.core.management.base import BaseCommand
from django.db import connection
from app.models import CustomUser


class Command(BaseCommand):
    help = 'Create CustomUser table manually'

    def handle(self, *args, **options):
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(CustomUser)
        self.stdout.write(
            self.style.SUCCESS('Successfully created CustomUser table')
        )
