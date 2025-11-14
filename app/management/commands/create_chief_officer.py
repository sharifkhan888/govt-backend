from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from app.models import Role, Permission, RolePermission, UserRole

class Command(BaseCommand):
    help = "Create or update a Chief Officer user with full permissions"

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, default='admin')
        parser.add_argument('--password', type=str, default='Admin123!')
        parser.add_argument('--inactive', action='store_true', help='Create user as inactive')

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        is_active = not options['inactive']

        # Ensure Chief Officer role exists/active
        role, _ = Role.objects.get_or_create(
            name='Chief Officer',
            defaults={'description': 'Master Admin'}
        )
        role.is_active = True
        role.save()

        # Seed core permissions to match RBAC middleware
        perms = [
            ('user', 'view_users', 'View Users'),
            ('user', 'add_users', 'Add Users'),
            ('user', 'edit_users', 'Edit Users'),
            ('user', 'delete_users', 'Delete Users'),
            ('transaction', 'view_transactions', 'View Transactions'),
            ('transaction', 'add_transactions', 'Add Transactions'),
            ('transaction', 'edit_transactions', 'Edit Transactions'),
            ('transaction', 'delete_transactions', 'Delete Transactions'),
            ('bank_account', 'view_banks', 'View Banks'),
            ('bank_account', 'add_banks', 'Add Banks'),
            ('bank_account', 'edit_banks', 'Edit Banks'),
            ('bank_account', 'delete_banks', 'Delete Banks'),
            ('contractor', 'view_contractors', 'View Contractors'),
            ('contractor', 'add_contractors', 'Add Contractors'),
            ('contractor', 'edit_contractors', 'Edit Contractors'),
            ('contractor', 'delete_contractors', 'Delete Contractors'),
            ('settings', 'view_settings', 'View Settings'),
            ('settings', 'edit_settings', 'Edit Settings'),
        ]
        for category, codename, name in perms:
            p, _ = Permission.objects.get_or_create(
                codename=codename,
                defaults={'name': name, 'description': name, 'category': category, 'is_active': True}
            )
            RolePermission.objects.get_or_create(role=role, permission=p)

        # Create or update the user
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={'role': 1, 'status': 'active'}
        )
        user.is_active = is_active
        user.role = 1  # keep integer role in sync (Chief Officer = 1)
        user.status = 'active' if is_active else 'inactive'
        user.set_password(password)
        user.save()

        # Link user to Chief Officer role
        UserRole.objects.get_or_create(user=user, role=role, defaults={'is_active': True})

        self.stdout.write(self.style.SUCCESS(
            f"Chief Officer user ready: username='{username}', password='{password}'"
        ))