from django.db import models
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from .models import WalletProfile
from .utils import verify_signed_message
import base64


class CustomAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, public_key=None, google_id=None, raw_signature=None, **kwargs):
        """
        Custom authentication backend supporting:
        1. Solana Wallet Signature (via public_key and raw_signature)
        2. Username/Password (or Email/Password)
        3. Google ID (for social login)
        """

        if request is not None and hasattr(request, 'path'):
            admin_paths = ['/admin/', '/admin-panel/']
            is_admin_request = any(request.path.startswith(path) for path in admin_paths)
            if is_admin_request:
                # This is an admin login attempt, let the ModelBackend handle it for standard auth.
                print("CustomAuthBackend: Skipping, path is for admin panel.")
                return None
            
        print(f"CustomAuthBackend: Attempting to authenticate with username: {username}, public_key: {public_key}, google_id: {google_id}")
        User = get_user_model()
        
        try:
            # === 1. Wallet-based authentication (Primary DApp Login) ===
            if public_key:
                print(f"CustomAuthBackend: Authenticating with public_key: {public_key}")
                
                # FIX: Prioritize raw_signature passed from the single-request flow (create_session)
                signed_message_base64 = raw_signature 
                if not signed_message_base64:
                    # Fallback to session check for older flows (e.g., reset password)
                    signed_message_base64 = request.session.get('signed_message')
                
                if not signed_message_base64:
                    print("CustomAuthBackend: No signed message found for verification")
                    return None

                signed_message = base64.b64decode(signed_message_base64)
                # Ensure this message exactly matches the one signed by the client
                original_message = f"Sign this message to log in or create an account. Wallet: {public_key}".encode('utf-8')

                print(f"CustomAuthBackend: Verifying signature for public_key: {public_key}")
                
                if not verify_signed_message(public_key, signed_message, original_message):
                    print("CustomAuthBackend: Signature verification failed")
                    return None

                profile = WalletProfile.objects.get(public_key=public_key)
                user = profile.user
                if user.is_active:
                    print(f"CustomAuthBackend: Authentication successful for user: {user.username}")
                    # Note: We do NOT clear the session message here, create_session handles it.
                    return user
                print("CustomAuthBackend: User is not active")
                return None

            # === 2. Username/password authentication (Web2 Fallback) ===
            if username and password:
                print(f"CustomAuthBackend: Authenticating with username: {username}")
                query = (
                    models.Q(username=username) |
                    models.Q(email=username) |
                    models.Q(secondary_identifier=username)
                )
                user = User.objects.filter(query).first()
                if user and user.check_password(password) and user.is_active:
                    print(f"CustomAuthBackend: Authentication successful for user: {user.username}")
                    return user
                print("CustomAuthBackend: Username/password authentication failed")
                return None

            # === 3. Google OAuth authentication (Social Login) ===
            if google_id:
                print(f"CustomAuthBackend: Authenticating with google_id: {google_id}")
                user = User.objects.filter(secondary_identifier=google_id).first()
                if user and user.is_active:
                    print(f"CustomAuthBackend: Authentication successful for user: {user.username}")
                    return user
                print("CustomAuthBackend: User does not exist for google_id, prompting signup")
                return None

        except (User.DoesNotExist, WalletProfile.DoesNotExist) as e:
            print(f"CustomAuthBackend: User or WalletProfile not found: {str(e)}")
            return None
        except Exception as e:
            print(f"CustomAuthBackend: Unexpected error: {str(e)}")
            return None
        print("CustomAuthBackend: No authentication method matched")
        return None

    def get_user(self, user_id):
        print(f"CustomAuthBackend: Retrieving user with ID: {user_id}")
        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
            print(f"CustomAuthBackend: Retrieved user: {user.username}")
            return user
        except User.DoesNotExist:
            print("CustomAuthBackend: User not found")
            return None