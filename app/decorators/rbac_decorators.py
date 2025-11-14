"""
RBAC Decorators for role-based permission checking
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
from ..models import UserRole, RolePermission, Permission


def has_permission(permission_codename):
    """
    Decorator to check if user has a specific permission
    
    Usage:
    @has_permission('view_users')
    def my_view(request):
        ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if request.path.startswith('/api/'):
                    return JsonResponse({
                        'error': 'Authentication required',
                        'message': 'Please login to access this resource.'
                    }, status=401)
                else:
                    messages.error(request, 'Please login to access this resource.')
                    return redirect('login')
            
            # Check if user has the required permission
            if not _user_has_permission(request.user, permission_codename):
                if request.path.startswith('/api/'):
                    return JsonResponse({
                        'error': 'Access Denied',
                        'message': f'You do not have permission: {permission_codename}'
                    }, status=403)
                else:
                    messages.error(request, 'You do not have permission to access this resource.')
                    return redirect('access_denied')
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def has_any_permission(*permission_codenames):
    """
    Decorator to check if user has any of the specified permissions
    
    Usage:
    @has_any_permission('view_users', 'edit_users')
    def my_view(request):
        ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if request.path.startswith('/api/'):
                    return JsonResponse({
                        'error': 'Authentication required',
                        'message': 'Please login to access this resource.'
                    }, status=401)
                else:
                    messages.error(request, 'Please login to access this resource.')
                    return redirect('login')
            
            # Check if user has any of the required permissions
            has_any = False
            for permission_codename in permission_codenames:
                if _user_has_permission(request.user, permission_codename):
                    has_any = True
                    break
            
            if not has_any:
                permission_list = ', '.join(permission_codenames)
                if request.path.startswith('/api/'):
                    return JsonResponse({
                        'error': 'Access Denied',
                        'message': f'You do not have any of these permissions: {permission_list}'
                    }, status=403)
                else:
                    messages.error(request, 'You do not have permission to access this resource.')
                    return redirect('access_denied')
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def has_all_permissions(*permission_codenames):
    """
    Decorator to check if user has all of the specified permissions
    
    Usage:
    @has_all_permissions('view_users', 'edit_users')
    def my_view(request):
        ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if request.path.startswith('/api/'):
                    return JsonResponse({
                        'error': 'Authentication required',
                        'message': 'Please login to access this resource.'
                    }, status=401)
                else:
                    messages.error(request, 'Please login to access this resource.')
                    return redirect('login')
            
            # Check if user has all of the required permissions
            missing_permissions = []
            for permission_codename in permission_codenames:
                if not _user_has_permission(request.user, permission_codename):
                    missing_permissions.append(permission_codename)
            
            if missing_permissions:
                permission_list = ', '.join(missing_permissions)
                if request.path.startswith('/api/'):
                    return JsonResponse({
                        'error': 'Access Denied',
                        'message': f'You are missing these permissions: {permission_list}'
                    }, status=403)
                else:
                    messages.error(request, 'You do not have permission to access this resource.')
                    return redirect('access_denied')
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def role_required(role_name):
    """
    Decorator to check if user has a specific role
    
    Usage:
    @role_required('Chief Officer')
    def my_view(request):
        ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if request.path.startswith('/api/'):
                    return JsonResponse({
                        'error': 'Authentication required',
                        'message': 'Please login to access this resource.'
                    }, status=401)
                else:
                    messages.error(request, 'Please login to access this resource.')
                    return redirect('login')
            
            # Check if user has the required role
            if not _user_has_role(request.user, role_name):
                if request.path.startswith('/api/'):
                    return JsonResponse({
                        'error': 'Access Denied',
                        'message': f'You do not have the required role: {role_name}'
                    }, status=403)
                else:
                    messages.error(request, 'You do not have permission to access this resource.')
                    return redirect('access_denied')
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


def any_role_required(*role_names):
    """
    Decorator to check if user has any of the specified roles
    
    Usage:
    @any_role_required('Chief Officer', 'Accountant Officer')
    def my_view(request):
        ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if request.path.startswith('/api/'):
                    return JsonResponse({
                        'error': 'Authentication required',
                        'message': 'Please login to access this resource.'
                    }, status=401)
                else:
                    messages.error(request, 'Please login to access this resource.')
                    return redirect('login')
            
            # Check if user has any of the required roles
            has_any = False
            for role_name in role_names:
                if _user_has_role(request.user, role_name):
                    has_any = True
                    break
            
            if not has_any:
                role_list = ', '.join(role_names)
                if request.path.startswith('/api/'):
                    return JsonResponse({
                        'error': 'Access Denied',
                        'message': f'You do not have any of these roles: {role_list}'
                    }, status=403)
                else:
                    messages.error(request, 'You do not have permission to access this resource.')
                    return redirect('access_denied')
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


# Helper functions
def _user_has_permission(user, permission_codename):
    """Check if user has a specific permission through their roles"""
    try:
        permission = Permission.objects.get(codename=permission_codename)
        user_roles = UserRole.objects.filter(user=user, is_active=True).select_related('role')
        
        for user_role in user_roles:
            if RolePermission.objects.filter(
                role=user_role.role,
                permission=permission
            ).exists():
                return True
        
        return False
    except Permission.DoesNotExist:
        return False


def _user_has_role(user, role_name):
    """Check if user has a specific role"""
    return UserRole.objects.filter(
        user=user,
        role__name=role_name,
        is_active=True
    ).exists()