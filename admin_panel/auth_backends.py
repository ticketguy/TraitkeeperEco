# admin_panel/auth_backends.py
from django.db import models
from django.contrib.auth.backends import ModelBackend
from admin_panel.models import AdminUser
import logging

logger = logging.getLogger(__name__)

class AdminAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # Check if the request is for an admin page
        if request is None or not hasattr(request, 'path'):
            logger.info("AdminAuthBackend: No request or path available, skipping authentication.")
            return None

        # Define admin-related paths
        admin_paths = ['/admin/', '/admin-panel/']
        is_admin_request = any(request.path.startswith(path) for path in admin_paths)

        if not is_admin_request:
            logger.info(f"AdminAuthBackend: Skipping authentication for non-admin path: {request.path}")
            return None

        logger.info(f"AdminAuthBackend: Attempting to authenticate username: {username} on admin path: {request.path}")
        if username and password:
            try:
                # Try username or email
                query = (
                    models.Q(username=username) |
                    models.Q(email=username)
                )
                user = AdminUser.objects.filter(query).first()
                
                if user:
                    logger.info(f"AdminAuthBackend: Found user: {user.username}")
                    # Check password
                    if not user.check_password(password):
                        logger.warning("AdminAuthBackend: Password does not match.")
                        return None
                    
                    # Check if active
                    if not user.is_active:
                        logger.warning("AdminAuthBackend: User account is inactive.")
                        return None
                    
                    # Check if staff
                    if not user.is_staff:
                        logger.warning("AdminAuthBackend: User is not staff.")
                        return None
                    
                    # All checks passed, return user
                    logger.info("AdminAuthBackend: Authentication successful.")
                    return user
                logger.warning("AdminAuthBackend: User not found.")
                return None
            except AdminUser.DoesNotExist:
                logger.warning("AdminAuthBackend: User does not exist.")
                return None
        
        logger.warning("AdminAuthBackend: No username or password provided.")
        return None

    def get_user(self, user_id):
        logger.info(f"AdminAuthBackend: Fetching user with ID: {user_id}")
        try:
            user = AdminUser.objects.get(pk=user_id)
            logger.info(f"AdminAuthBackend: Found user with ID: {user_id}")
            return user
        except AdminUser.DoesNotExist:
            logger.warning(f"AdminAuthBackend: User with ID {user_id} does not exist.")
            return None