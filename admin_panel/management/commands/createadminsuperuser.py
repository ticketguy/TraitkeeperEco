# admin_panel/management/commands/createadminsuperuser.py
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from admin_panel.models import AdminUser
from django.core.management import call_command
from django.contrib.auth.management.commands import createsuperuser

class Command(createsuperuser.Command):
    help = 'Create a superuser for the AdminUser model'

    def handle(self, *args, **options):
        # Temporarily override the UserModel to AdminUser
        self.UserModel = AdminUser
        options['username_field'] = 'username'
        super().handle(*args, **options)