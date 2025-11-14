"""
Management command to backfill UserRole from User.role choices
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from app.models import Role, UserRole


class Command(BaseCommand):
    help = 'Sync UserRole records based on User.role choice for all users'

    ROLE_NAME_BY_ID = {
        1: 'Chief Officer',
        2: 'Accountant Officer',
        3: 'Auditor',
        4: 'Clerk',
    }

    def handle(self, *args, **options):
        User = get_user_model()
        self.stdout.write(self.style.SUCCESS('Syncing UserRole from User.role...'))
        created_count = 0
        updated_count = 0
        skipped_count = 0

        for user in User.objects.all():
            role_name = self.ROLE_NAME_BY_ID.get(getattr(user, 'role', None))
            if not role_name:
                skipped_count += 1
                continue
            try:
                role = Role.objects.get(name=role_name)
            except Role.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"Role not found: {role_name}; user {user.id} skipped"))
                skipped_count += 1
                continue

            ur, created = UserRole.objects.get_or_create(user=user, role=role, defaults={'is_active': True})
            if created:
                created_count += 1
                self.stdout.write(f"Created UserRole: user={user.id} role={role.name}")
            else:
                if not ur.is_active:
                    ur.is_active = True
                    ur.save(update_fields=['is_active'])
                    updated_count += 1
                    self.stdout.write(f"Activated UserRole: user={user.id} role={role.name}")
                else:
                    skipped_count += 1

        self.stdout.write(self.style.SUCCESS('Sync completed'))
        self.stdout.write(f'Created: {created_count}, Activated: {updated_count}, Skipped: {skipped_count}')

