"""
Management command to setup RBAC roles and permissions
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from app.models import Role, Permission, RolePermission, UserRole

User = get_user_model()


class Command(BaseCommand):
    help = 'Setup RBAC roles and permissions for the application'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Setting up RBAC roles and permissions...'))
        
        # Create permissions
        permissions_data = [
            # User management permissions
            {'codename': 'view_users', 'name': 'Can view users', 'description': 'View user information'},
            {'codename': 'add_users', 'name': 'Can add users', 'description': 'Add new users'},
            {'codename': 'edit_users', 'name': 'Can edit users', 'description': 'Edit existing users'},
            {'codename': 'delete_users', 'name': 'Can delete users', 'description': 'Delete users'},
            
            # Transaction permissions
            {'codename': 'view_transactions', 'name': 'Can view transactions', 'description': 'View transaction records'},
            {'codename': 'add_transactions', 'name': 'Can add transactions', 'description': 'Add new transactions'},
            {'codename': 'edit_transactions', 'name': 'Can edit transactions', 'description': 'Edit existing transactions'},
            {'codename': 'delete_transactions', 'name': 'Can delete transactions', 'description': 'Delete transactions'},
            
            # Bank account permissions
            {'codename': 'view_banks', 'name': 'Can view bank accounts', 'description': 'View bank account information'},
            {'codename': 'add_banks', 'name': 'Can add bank accounts', 'description': 'Add new bank accounts'},
            {'codename': 'edit_banks', 'name': 'Can edit bank accounts', 'description': 'Edit existing bank accounts'},
            {'codename': 'delete_banks', 'name': 'Can delete bank accounts', 'description': 'Delete bank accounts'},
            
            # Contractor permissions
            {'codename': 'view_contractors', 'name': 'Can view contractors', 'description': 'View contractor information'},
            {'codename': 'add_contractors', 'name': 'Can add contractors', 'description': 'Add new contractors'},
            {'codename': 'edit_contractors', 'name': 'Can edit contractors', 'description': 'Edit existing contractors'},
            {'codename': 'delete_contractors', 'name': 'Can delete contractors', 'description': 'Delete contractors'},
            
            # Settings permissions
            {'codename': 'view_settings', 'name': 'Can view settings', 'description': 'View system settings'},
            {'codename': 'edit_settings', 'name': 'Can edit settings', 'description': 'Edit system settings'},
            
            # Report permissions
            {'codename': 'view_reports', 'name': 'Can view reports', 'description': 'View financial reports'},
            {'codename': 'export_reports', 'name': 'Can export reports', 'description': 'Export financial reports'},
            
            # Backup permissions
            {'codename': 'backup_data', 'name': 'Can backup data', 'description': 'Create data backups'},
            {'codename': 'restore_data', 'name': 'Can restore data', 'description': 'Restore data from backups'},
        ]
        
        # Create permissions
        created_permissions = []
        for perm_data in permissions_data:
            permission, created = Permission.objects.get_or_create(
                codename=perm_data['codename'],
                defaults={
                    'name': perm_data['name'],
                    'description': perm_data['description']
                }
            )
            if created:
                created_permissions.append(permission)
                self.stdout.write(f"Created permission: {permission.codename}")
            else:
                self.stdout.write(f"Permission already exists: {permission.codename}")
        
        # Create roles
        roles_data = [
            {
                'name': 'Chief Officer',
                'description': 'Master Administrator with full access to all system features',
                'permissions': [p['codename'] for p in permissions_data]  # All permissions
            },
            {
                'name': 'Accountant Officer',
                'description': 'Financial operator with limited permissions per requirements',
                'permissions': [
                    # Bank account: add, edit, view (no delete)
                    'view_banks', 'add_banks', 'edit_banks',
                    # Contractor: view-only
                    'view_contractors',
                    # Payment entry (transactions): add, delete, view (no edit)
                    'view_transactions', 'add_transactions', 'delete_transactions',
                    # Reports: generate + export
                    'view_reports', 'export_reports',
                    # Backup: create-only
                    'backup_data'
                ]
            },
            {
                'name': 'Auditor',
                'description': 'Auditing access with limited create rights on contractors',
                'permissions': [
                    # Bank account: view-only
                    'view_banks',
                    # Contractor: add, edit, view (no delete)
                    'view_contractors', 'add_contractors', 'edit_contractors',
                    # Payment entry: view-only
                    'view_transactions',
                    # Reports: generate + export
                    'view_reports', 'export_reports',
                    # Backup: create-only
                    'backup_data'
                ]
            },
            {
                'name': 'Clerk',
                'description': 'Basic view and reporting access as per requirements',
                'permissions': [
                    # Payment entry: view-only
                    'view_transactions',
                    # Reports: generate + export
                    'view_reports', 'export_reports'
                ]
            }
        ]
        
        # Create roles and assign permissions
        for role_data in roles_data:
            role, created = Role.objects.get_or_create(
                name=role_data['name'],
                defaults={'description': role_data['description']}
            )
            
            if created:
                self.stdout.write(f"Created role: {role.name}")
            else:
                self.stdout.write(f"Role already exists: {role.name}")
            
            # Assign permissions to role (ensure present)
            desired = set(role_data['permissions'])
            for perm_codename in desired:
                try:
                    permission = Permission.objects.get(codename=perm_codename)
                    role_permission, rp_created = RolePermission.objects.get_or_create(
                        role=role,
                        permission=permission
                    )
                    if rp_created:
                        self.stdout.write(f"  - Assigned permission: {perm_codename}")
                    else:
                        self.stdout.write(f"  - Permission already assigned: {perm_codename}")
                except Permission.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f"  - Permission not found: {perm_codename}")
                    )

            # Cleanup: remove any extra permissions not in desired set
            try:
                current_rps = RolePermission.objects.filter(role=role).select_related('permission')
                for rp in current_rps:
                    codename = getattr(rp.permission, 'codename', None)
                    if codename and codename not in desired:
                        rp.delete()
                        self.stdout.write(f"  - Removed extra permission: {codename}")
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"  - Cleanup skipped due to error: {exc}"))
        
        self.stdout.write(self.style.SUCCESS('\nRBAC setup completed successfully!'))
        self.stdout.write(self.style.SUCCESS(f'Created {len(created_permissions)} new permissions'))
        
        # Display summary
        self.stdout.write('\nRole Summary:')
        for role_data in roles_data:
            role = Role.objects.get(name=role_data['name'])
            permission_count = RolePermission.objects.filter(role=role).count()
            self.stdout.write(f"  - {role.name}: {permission_count} permissions")
        
        self.stdout.write('\nNext steps:')
        self.stdout.write('1. Assign roles to users using the admin interface or UserRole model')
        self.stdout.write('2. Test the RBAC system with different user roles')
        self.stdout.write('3. Update your views with the appropriate decorators')
