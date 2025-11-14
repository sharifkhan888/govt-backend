"""
Example views demonstrating RBAC usage
"""
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from .decorators import (
    has_permission, 
    has_any_permission, 
    has_all_permissions,
    role_required, 
    any_role_required
)


@method_decorator(login_required, name='dispatch')
class RBACExampleView(APIView):
    """Example view demonstrating RBAC decorators"""
    
    @has_permission('view_users')
    def get(self, request):
        """Only users with 'view_users' permission can access this"""
        return Response({
            'message': 'You have permission to view users',
            'user': request.user.username,
            'role': request.user.get_role_display()
        })
    
    @has_permission('add_users')
    def post(self, request):
        """Only users with 'add_users' permission can access this"""
        return Response({
            'message': 'You have permission to add users',
            'user': request.user.username
        })


@method_decorator(login_required, name='dispatch')
class MultiPermissionExampleView(APIView):
    """Example view demonstrating multiple permission decorators"""
    
    @has_any_permission('edit_users', 'delete_users')
    def get(self, request):
        """Users with either 'edit_users' OR 'delete_users' can access"""
        return Response({
            'message': 'You have either edit or delete user permissions',
            'user': request.user.username
        })
    
    @has_all_permissions('view_users', 'edit_users')
    def post(self, request):
        """Users must have BOTH 'view_users' AND 'edit_users' permissions"""
        return Response({
            'message': 'You have both view and edit user permissions',
            'user': request.user.username
        })


@method_decorator(login_required, name='dispatch')
class RoleBasedExampleView(APIView):
    """Example view demonstrating role-based access"""
    
    @role_required('Chief Officer')
    def get(self, request):
        """Only Chief Officer can access this"""
        return Response({
            'message': 'Welcome, Chief Officer!',
            'user': request.user.username
        })
    
    @any_role_required('Accountant Officer', 'Chief Officer')
    def post(self, request):
        """Accountant Officer OR Chief Officer can access this"""
        return Response({
            'message': 'Welcome, Financial Officer!',
            'user': request.user.username
        })


@login_required
def rbac_test_page(request):
    """Template view demonstrating RBAC in templates"""
    from .decorators import _user_has_permission, _user_has_role
    
    # Check current user's permissions
    user_permissions = {
        'can_view_users': _user_has_permission(request.user, 'view_users'),
        'can_add_users': _user_has_permission(request.user, 'add_users'),
        'can_edit_users': _user_has_permission(request.user, 'edit_users'),
        'can_delete_users': _user_has_permission(request.user, 'delete_users'),
        'can_view_transactions': _user_has_permission(request.user, 'view_transactions'),
        'can_add_transactions': _user_has_permission(request.user, 'add_transactions'),
        'can_edit_transactions': _user_has_permission(request.user, 'edit_transactions'),
        'can_delete_transactions': _user_has_permission(request.user, 'delete_transactions'),
    }
    
    # Check current user's roles
    user_roles = {
        'is_chief_officer': _user_has_role(request.user, 'Chief Officer'),
        'is_accountant_officer': _user_has_role(request.user, 'Accountant Officer'),
        'is_auditor': _user_has_role(request.user, 'Auditor'),
        'is_clerk': _user_has_role(request.user, 'Clerk'),
    }
    
    context = {
        'user_permissions': user_permissions,
        'user_roles': user_roles,
    }
    
    return render(request, 'app/rbac_test.html', context)