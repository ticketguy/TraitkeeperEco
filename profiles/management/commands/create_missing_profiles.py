"""
Management command to create Profile objects for users that don't have one.
Run this to fix existing users after adding the Profile model.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from profiles.models import Profile

User = get_user_model()


class Command(BaseCommand):
    help = 'Creates Profile objects for all users that do not have one'

    def handle(self, *args, **options):
        users_without_profiles = []

        # Find all users without profiles
        for user in User.objects.all():
            try:
                # Try to access the profile
                _ = user.profile
            except Profile.DoesNotExist:
                users_without_profiles.append(user)

        if not users_without_profiles:
            self.stdout.write(self.style.SUCCESS('All users already have profiles!'))
            return

        # Create profiles for users that don't have one
        created_count = 0
        for user in users_without_profiles:
            Profile.objects.create(user=user)
            created_count += 1
            self.stdout.write(f'Created profile for user: {user.username}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created {created_count} profile(s)'
            )
        )
