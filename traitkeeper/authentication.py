from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import Token
from django.utils import timezone

class ExpiringTokenAuthentication(BaseAuthentication):
    """
    Custom token authentication for external users with expiry check.
    Requires both the token key (in Authorization header) and the associated email (in X-Email header).
    """
    model = Token

    def authenticate(self, request):
        # Extract the Authorization header
        auth = request.META.get('HTTP_AUTHORIZATION', '').split()
        if not auth or auth[0].lower() != 'token':
            return None  # No token provided, let other authentication classes handle it

        if len(auth) == 1:
            msg = 'Invalid token header. No credentials provided.'
            raise AuthenticationFailed(msg)
        elif len(auth) > 2:
            msg = 'Invalid token header. Token string should not contain spaces.'
            raise AuthenticationFailed(msg)

        token_key = auth[1]

        # Extract the email from the X-Email header
        email = request.META.get('HTTP_X_EMAIL', None)
        if not email:
            raise AuthenticationFailed('X-Email header is required.')

        return self.authenticate_credentials(token_key, email)

    def authenticate_credentials(self, key, email):
        """
        Authenticate the token key and email.
        Returns a pseudo-user (None) and the token object if valid.
        """
        try:
            token = self.model.objects.get(key=key)
        except self.model.DoesNotExist:
            raise AuthenticationFailed('Invalid token.')

        # Check if the token has expired
        if token.is_expired():
            raise AuthenticationFailed('Token has expired.')

        # Validate that the provided email matches the token's email
        if token.email != email:
            raise AuthenticationFailed('Email does not match the token.')

        # Since this token is for an external user, there is no associated CustomUser.
        # Return None as the user (pseudo-user) and the token object.
        return (None, token)

    def authenticate_header(self, request):
        return 'Token'