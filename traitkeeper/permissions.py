from rest_framework.permissions import BasePermission

class HasValidToken(BasePermission):
    """
    Custom permission to allow access if a valid token is present.
    Unlike IsAuthenticated, this does not require request.user to be a user instance.
    Used for external users who authenticate with a token but have no associated user.
    """
    def has_permission(self, request, view):
        # Allow access if request.auth exists (i.e., a valid token was found)
        return request.auth is not None