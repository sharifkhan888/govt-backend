"""
RBAC Middleware for permission checking
"""
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages
from ..models import UserRole, RolePermission, Permission


class RBACMiddleware:
    """Middleware to check user permissions based on RBAC system"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Define permission mappings for different URL patterns
        self.permission_map = {
            # User management permissions
            '/api/users/': {
                'GET': 'view_users',
                'POST': 'add_users',
                'PUT': 'edit_users',
                'DELETE': 'delete_users',
                'PATCH': 'edit_users'
            },
            # Transaction permissions
            '/api/transactions/': {
                'GET': 'view_transactions',
                'POST': 'add_transactions',
                'PUT': 'edit_transactions',
                'DELETE': 'delete_transactions',
                'PATCH': 'edit_transactions'
            },
            # Bank account permissions
            '/api/bank-accounts/': {
                'GET': 'view_banks',
                'POST': 'add_banks',
                'PUT': 'edit_banks',
                'DELETE': 'delete_banks',
                'PATCH': 'edit_banks'
            },
            # Contractor permissions
            '/api/contractors/': {
                'GET': 'view_contractors',
                'POST': 'add_contractors',
                'PUT': 'edit_contractors',
                'DELETE': 'delete_contractors',
                'PATCH': 'edit_contractors'
            },
            # Settings permissions
            '/api/settings/': {
                'GET': 'view_settings',
                'POST': 'edit_settings',
                'PUT': 'edit_settings',
                'DELETE': 'edit_settings',
                'PATCH': 'edit_settings'
            },
            '/api/settings/image-path/': {
                'GET': None
            },
            # Report permissions (read/export via GET)
            '/api/reports/': {
                'GET': 'view_reports'
            },
            # Backup permissions (action handled in view)
            '/api/backup/': {
                'POST': 'backup_data'
            }
        }
    
    def __call__(self, request):
        # Skip permission checking for certain paths
        if self._should_skip_permission_check(request):
            return self.get_response(request)
        
        # Check if user is authenticated
        if not request.user.is_authenticated:
            return self.get_response(request)
        
        # Check permissions for API endpoints
        if request.path.startswith('/api/'):
            if not self._check_api_permission(request):
                return self._access_denied_response(request)
        
        return self.get_response(request)
    
    def _should_skip_permission_check(self, request):
        """Skip permission checking for certain paths"""
        skip_paths = [
            '/admin/',
            '/api/auth/',
            '/api/token/',
            '/api/login/',
            '/api/logout/',
            '/static/',
            '/media/',
            '/access-denied/'
        ]
        
        return any(request.path.startswith(path) for path in skip_paths)
    
    def _check_api_permission(self, request):
        """Check if user has permission for the API endpoint"""
        user = request.user
        method = request.method
        path = request.path
        
        # Find the matching permission for this path and method
        required_permission = self._get_required_permission(path, method)
        if not required_permission:
            # No specific permission required for this endpoint
            return True
        
        # Get user's roles
        user_roles = UserRole.objects.filter(user=user, is_active=True).select_related('role')
        if not user_roles.exists():
            return False
        
        # Check if any of the user's roles have the required permission
        for user_role in user_roles:
            role = user_role.role
            if self._role_has_permission(role, required_permission):
                return True
        
        return False
    
    def _get_required_permission(self, path, method):
        """Get the required permission for a given path and method"""
        # Check exact matches first
        if path in self.permission_map:
            return self.permission_map[path].get(method)
        
        # Check for path patterns (e.g., /api/users/123/ should match /api/users/)
        for pattern, permissions in self.permission_map.items():
            if path.startswith(pattern):
                return permissions.get(method)
        
        return None
    
    def _role_has_permission(self, role, permission_codename):
        """Check if a role has a specific permission"""
        try:
            permission = Permission.objects.get(codename=permission_codename)
            return RolePermission.objects.filter(
                role=role,
                permission=permission
            ).exists()
        except Permission.DoesNotExist:
            return False
    
    def _access_denied_response(self, request):
        """Return access denied response"""
        if request.path.startswith('/api/'):
            from django.http import JsonResponse
            return JsonResponse({
                'error': 'Access Denied',
                'message': 'You do not have permission to access this resource.'
            }, status=403)
        else:
            messages.error(request, 'You do not have permission to access this resource.')
            return redirect('access_denied')
