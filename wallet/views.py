import json
import base64
import random
import string
from django.http import JsonResponse, HttpResponseRedirect
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import models
from django.conf import settings
from .models import WalletProfile, PasswordResetCode
from notifications.models import Notification
from django.core.mail import send_mail
from datetime import timedelta
from django.utils.dateparse import parse_datetime
from django.contrib.auth import login
from .utils import verify_signed_message, wallet_connected_required
from django.utils import timezone
from decimal import Decimal
from nft_data.services import NFTDataService
User = get_user_model()

@login_required
def user_profile_settings(request):
    user = request.user
    # Updated for multiple wallets support
    user_wallets = user.wallets.all() if hasattr(user, 'wallets') else []
    primary_wallet = WalletProfile.get_primary_wallet(user) if user_wallets.exists() else None
    google_linked = user.secondary_identifier is not None and user.secondary_identifier.startswith('google_')
    email_linked = user.email is not None and user.has_usable_password()

    if request.method == 'POST':
        if 'unlink_wallet' in request.POST:
            # This is handled by profiles app now - redirect there
            return redirect('profiles:settings_wallets')
        elif 'unlink_google' in request.POST:
            if google_linked:
                user.secondary_identifier = None
                user.save()
                return redirect('wallet:user_profile_settings')
        elif 'set_email_password' in request.POST:
            email = request.POST.get('email')
            password = request.POST.get('password')
            if email and password:
                if User.objects.filter(email=email).exclude(id=user.id).exists():
                    return render(request, 'wallet/user_profile_settings.html', {
                        'error': 'Email is already in use.',
                        'user_wallets': user_wallets,
                        'primary_wallet': primary_wallet,
                        'google_linked': google_linked,
                        'email_linked': email_linked,
                    })
                user.email = email
                user.set_password(password)
                user.save()
                return redirect('wallet:user_profile_settings')

    return render(request, 'wallet/user_profile_settings.html', {
        'user_wallets': user_wallets,
        'primary_wallet': primary_wallet,
        'google_linked': google_linked,
        'email_linked': email_linked,
    })



@require_POST
def email_signup(request):
    username = request.POST.get('username')
    email = request.POST.get('email')
    password = request.POST.get('password')

    if not username or not email or not password:
        print(f"Email signup failed: Missing fields - username: {username}, email: {email}, password: {'provided' if password else 'missing'}")
        return JsonResponse({'error': 'Username, email, and password are required'}, status=400)

    # Check if username or email is already taken
    if User.objects.filter(username=username).exists():
        print(f"Email signup failed: Username already taken - {username}")
        return JsonResponse({'error': 'Username is already taken'}, status=400)
    if User.objects.filter(email=email).exists():
        print(f"Email signup failed: Email already in use - {email}")
        return JsonResponse({'error': 'Email is already in use'}, status=400)

    # Generate a 6-digit verification code
    verification_code = ''.join(random.choices(string.digits, k=6))
    print(f"Generated verification code for {email}: {verification_code}")

    # Store signup details, code, and creation time in session
    request.session['signup_data'] = {
        'username': username,
        'email': email,
        'password': password,
        'verification_code': verification_code,
        'created_at': timezone.now().isoformat()  # Store the creation time as an ISO string
    } 
    request.session.set_expiry(300)
    # Send the verification code via email
    email_error = None
    try:
        send_mail(
            subject='Email Verification Code',
            message=f'Your email verification code is: {verification_code}\nThis code will expire in 5 minutes.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False
        )
        print(f"Verification code sent to {email}")
    except Exception as e:
        print(f"Error sending verification email to {email}: {str(e)}")
        print(f"DEBUG: Verification code for {email}: {verification_code}")
        email_error = 'Failed to send verification email. Please try again later.'

    response_data = {'status': 'verification_required', 'email': email}
    if email_error:
        response_data['email_error'] = email_error
    return JsonResponse(response_data)





@require_POST
def verify_email_code(request):
    try:
        code = request.POST.get('code')
        signup_data = request.session.get('signup_data')

        if not signup_data:
            print("Email verification failed: No signup data found in session")
            return JsonResponse({'error': 'Code expired. Please start the signup process again.'}, status=400)

        if not code:
            print("Email verification failed: Verification code missing")
            return JsonResponse({'error': 'Verification code is required'}, status=400)

        # Check if the code has expired (5 minutes)
        created_at = parse_datetime(signup_data.get('created_at'))
        if not created_at:
            print("Email verification failed: No creation timestamp found in session")
            request.session.pop('signup_data', None)  # Clear invalid session data
            return JsonResponse({'error': 'Invalid signup data. Please start the signup process again.'}, status=400)

        expiration_time = created_at + timedelta(minutes=5)
        current_time = timezone.now()
        if current_time > expiration_time:
            print(f"Email verification failed: Code expired - created_at: {created_at}, current_time: {current_time}")
            request.session.pop('signup_data', None)  # Clear expired session data
            return JsonResponse({'error': 'Verification code has expired. Please start the signup process again.'}, status=400)

        # Check if the code matches
        expected_code = signup_data.get('verification_code')
        if code != expected_code:
            print(f"Email verification failed: Invalid code - entered: {code}, expected: {expected_code}")
            return JsonResponse({'error': 'Invalid verification code'}, status=400)

        # Create the user
        username = signup_data['username']
        email = signup_data['email']
        password = signup_data['password']

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )
        print(f"User created: {user.username}")

        # Log the user in
        login(request, user, backend='wallet.auth_backends.CustomAuthBackend')

        # Clear signup data from session
        request.session.pop('signup_data', None)

        return JsonResponse({
            'status': 'success',
            'username': user.username,
            'profile_picture': user.profile_picture if user.profile_picture else ''
        })
    except Exception as e:
        print(f"Error in verify_email_code: {str(e)}")
        return JsonResponse({'error': 'Failed to verify code', 'details': str(e)}, status=500)

@require_POST
def email_login(request):
    username_or_email = request.POST.get('username_or_email')
    password = request.POST.get('password')

    if not username_or_email or not password:
        print(f"Email login failed: Missing fields - username_or_email: {username_or_email}, password: {'provided' if password else 'missing'}")
        return JsonResponse({'error': 'Username or email and password are required'}, status=400)

    email_exists = User.objects.filter(
        models.Q(email=username_or_email) |
        models.Q(username=username_or_email)
    ).exists()

    print(f"Email login: Checking user with username/email: {username_or_email}, exists: {email_exists}")

    user = authenticate(request, username=username_or_email, password=password)
    if user is not None:
        print(f"Email login successful for user: {user.username}")
        login(request, user, backend='wallet.auth_backends.CustomAuthBackend')
        return JsonResponse({
            'status': 'success',
            'username': user.username,
            'profile_picture': user.profile_picture if user.profile_picture else ''
        }, status=200)
    else:
        print(f"Email login failed for username/email: {username_or_email}, email_exists: {email_exists}")
        return JsonResponse({
            'error': 'Invalid username/email or password',
            'exists': email_exists
        }, status=200)
    

@require_POST
def google_signup(request):
    try:
        google_data = request.session.get('google_signup_data')
        if not google_data:
            return JsonResponse({'error': 'No Google signup data found'}, status=400)

        google_id = google_data.get('google_id')
        email = google_data.get('email')
        username = request.POST.get('username', f"google_{google_id[:8]}")

        if User.objects.filter(email=email).exists():
            return JsonResponse({'error': 'Email is already in use'}, status=400)
        if User.objects.filter(username=username).exists():
            return JsonResponse({'error': 'Username is already taken'}, status=400)

        # Create the user
        user = User.objects.create_user(
            username=username,
            email=email,
            secondary_identifier=google_id
        )
        login(request, user)

        # Clear session data
        request.session.pop('google_signup_data', None)

        return JsonResponse({
            'status': 'success',
            'username': user.username,
            'profile_picture': user.profile_picture if user.profile_picture else ''
        })
    except Exception as e:
        print(f"Error in google_signup: {str(e)}")
        return JsonResponse({'error': 'Signup failed', 'details': str(e)}, status=500)


@require_GET
def get_google_signup_data(request):
    google_data = request.session.get('google_signup_data')
    if google_data:
        return JsonResponse({'status': 'success', 'google_data': google_data})
    return JsonResponse({'status': 'not_found'})

@require_POST
def store_signed_message(request):
    try:
        print(f"Received request to store signed message: {request.body}")
        data = json.loads(request.body)
        signed_message_base64 = data.get('signed_message')
        if not signed_message_base64:
            print("Signed message is missing in request body")
            return JsonResponse({'error': 'Signed message is required'}, status=400)

        request.session['signed_message'] = signed_message_base64
        print(f"Stored signed message in session: {signed_message_base64}")
        return JsonResponse({'status': 'success'})
    except json.JSONDecodeError as e:
        print(f"JSON decode error in store_signed_message: {str(e)}")
        return JsonResponse({'error': 'Invalid JSON format', 'details': str(e)}, status=400)
    except Exception as e:
        print(f"Error in store_signed_message: {str(e)}")
        return JsonResponse({'error': 'Failed to store signed message', 'details': str(e)}, status=500)



@require_POST
def create_session(request):
    try:
        data = json.loads(request.body)
        public_key = data.get('public_key')
        # FIX: Read signed message directly from the request body
        signed_message_base64 = data.get('signed_message') 

        if not public_key or not signed_message_base64:
            return JsonResponse({'error': 'Public key and signed message are required'}, status=400)

        signed_message = base64.b64decode(signed_message_base64)

        # The message the user was prompted to sign on their wallet
        original_message = f"Sign this message to log in or create an account. Wallet: {public_key}".encode('utf-8')
        
        if not verify_signed_message(public_key, signed_message, original_message):
            return JsonResponse({'error': 'Signature verification failed'}, status=400)

        with transaction.atomic():
            # 1. Get or Create User and WalletProfile
            profile, user, created = WalletProfile.get_or_create_profile_and_user(public_key=public_key)

            # 2. Authenticate using the signature data
            # The CustomAuthBackend must be updated to accept raw_signature
            user = authenticate(
                request, 
                public_key=public_key, 
                raw_signature=signed_message_base64 # Passed for backend verification
            ) 
            
            if user is None:
                return JsonResponse({'error': 'Authentication failed: User not found/active'}, status=400)
            
            # 3. Finalize Session
            # We clear any stale message stored by the old two-step flow
            request.session.pop('signed_message', None) 
            
            login(request, user, backend='wallet.auth_backends.CustomAuthBackend')
            request.session['wallet_connected'] = True
            request.session['wallet_public_key'] = public_key

            return JsonResponse({
                'status': 'success',
                'username': user.username,
                'profile_picture': user.profile_picture if user.profile_picture else ''
            })

    except Exception as e:
        print(f"Error in create_session: {str(e)}")
        return JsonResponse({
            'error': 'Server error',
            'details': str(e)
        }, status=500)
    
@require_POST
def verify_session(request):
    try:
        data = json.loads(request.body)
        public_key = data.get('public_key')

        if not public_key:
            print("Verify session: Public key is required")
            return JsonResponse({'error': 'Public key is required'}, status=400)

        # Check if the session indicates the user is logged in with the correct public key
        wallet_connected = request.session.get('wallet_connected', False)
        session_public_key = request.session.get('wallet_public_key')

        print(f"Verify session: wallet_connected={wallet_connected}, session_public_key={session_public_key}, provided_public_key={public_key}")

        if not wallet_connected or session_public_key != public_key:
            print("Verify session: Session verification failed")
            return JsonResponse({'error': 'Session verification failed'}, status=400)

        # Verify the user exists and is active
        profile = WalletProfile.objects.get(public_key=public_key)
        user = profile.user
        if not user.is_active:
            print("Verify session: User is not active")
            return JsonResponse({'error': 'User is not active'}, status=400)

        return JsonResponse({
            'status': 'success',
            'username': user.username,
            'profile_picture': user.profile_picture if user.profile_picture else ''
        })

    except WalletProfile.DoesNotExist:
        print("Verify session: WalletProfile not found")
        return JsonResponse({'error': 'WalletProfile not found'}, status=400)
    except Exception as e:
        print(f"Error in verify_session: {str(e)}")
        return JsonResponse({'error': 'Server error', 'details': str(e)}, status=500)


@require_POST
def disconnect_wallet(request):
    try:
        logout(request)
        request.session['wallet_connected'] = False
        request.session['wallet_public_key'] = None
        return JsonResponse({'status': 'success'})
    except Exception as e:
        print(f"Wallet disconnection error: {str(e)}")
        return JsonResponse({'error': 'Disconnection failed', 'details': str(e)}, status=500)

@require_POST
@login_required
def link_wallet(request):
    try:
        data = json.loads(request.body)
        public_key = data.get('public_key')
        # FIX: Read signed message directly from the request body
        signed_message_base64 = data.get('signed_message') 

        if not public_key or not signed_message_base64:
             return JsonResponse({'error': 'Public key and signed message are required'}, status=400)

        signed_message = base64.b64decode(signed_message_base64)

        # NOTE: The client-side JS used: "Sign this message to link. Wallet: {public_key}"
        original_message = f"Sign this message to link. Wallet: {public_key}".encode('utf-8')

        if not verify_signed_message(public_key, signed_message, original_message):
            return JsonResponse({'error': 'Signature verification failed'}, status=400)

        # NOTE: No session pop needed here either
        
        user = request.user
        # Check if this wallet is already linked to THIS user (existing check is good)
        if WalletProfile.objects.filter(user=user, public_key=public_key).exists():
            return JsonResponse({'error': 'This wallet is already linked to your account'}, status=400)

        # Check if wallet is linked to ANOTHER user (existing check is good)
        if WalletProfile.objects.filter(public_key=public_key).exists():
            return JsonResponse({'error': 'This wallet is already linked to another account'}, status=400)

        with transaction.atomic():
            WalletProfile.objects.create(user=user, public_key=public_key)

        request.session['wallet_connected'] = True
        request.session['wallet_public_key'] = public_key

        return JsonResponse({'status': 'success'})
    except Exception as e:
        print(f"Error in link_wallet: {str(e)}")
        return JsonResponse({'error': 'Failed to link wallet', 'details': str(e)}, status=500)

@require_GET
@login_required
def link_google(request):
    return redirect('social:begin', 'google-oauth2')

@require_POST
def initiate_password_reset(request):
    try:
        data = json.loads(request.body)
        email = data.get('email')

        if not email:
            return JsonResponse({'error': 'Email is required'}, status=400)

        user = User.objects.filter(
            models.Q(email=email) |
            models.Q(username=email) |
            models.Q(secondary_identifier=email)
        ).first()

        if not user:
            return JsonResponse({'error': 'No account found with this email'}, status=400)

        # Determine available reset methods
        # Updated for multiple wallets support
        has_wallet = user.wallets.exists() if hasattr(user, 'wallets') else False
        has_email = user.email is not None

        if not (has_wallet or has_email):
            return JsonResponse({'error': 'No reset methods available. Please contact support.'}, status=400)

        return JsonResponse({
            'status': 'success',
            'methods': {
                'wallet': has_wallet,
                'email': has_email
            },
            'email': user.email
        })
    except Exception as e:
        print(f"Error in initiate_password_reset: {str(e)}")
        return JsonResponse({'error': 'Failed to initiate password reset', 'details': str(e)}, status=500)

@require_POST
def send_password_reset_code(request):
    try:
        data = json.loads(request.body)
        email = data.get('email')

        user = User.objects.filter(
            models.Q(email=email) |
            models.Q(username=email) |
            models.Q(secondary_identifier=email)
        ).first()

        if not user or not user.email:
            return JsonResponse({'error': 'No account found with this email'}, status=400)

        # Generate a 6-digit code
        code = ''.join(random.choices(string.digits, k=6))
        PasswordResetCode.objects.create(user=user, code=code)

        # Send the code via email
        send_mail(
            subject='Password Reset Code',
            message=f'Your password reset code is: {code}\nThis code will expire in 15 minutes.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False
        )

        return JsonResponse({'status': 'success', 'message': 'Password reset code sent to your email'})
    except Exception as e:
        print(f"Error in send_password_reset_code: {str(e)}")
        return JsonResponse({'error': 'Failed to send password reset code', 'details': str(e)}, status=500)

@require_POST
def verify_password_reset_code(request):
    try:
        data = json.loads(request.body)
        email = data.get('email')
        code = data.get('code')

        user = User.objects.filter(
            models.Q(email=email) |
            models.Q(username=email) |
            models.Q(secondary_identifier=email)
        ).first()

        if not user:
            return JsonResponse({'error': 'No account found with this email'}, status=400)

        reset_code = PasswordResetCode.objects.filter(user=user, code=code).first()
        if not reset_code or not reset_code.is_valid():
            return JsonResponse({'error': 'Invalid or expired code'}, status=400)

        reset_code.used = True
        reset_code.save()

        return JsonResponse({'status': 'success', 'message': 'Code verified'})
    except Exception as e:
        print(f"Error in verify_password_reset_code: {str(e)}")
        return JsonResponse({'error': 'Failed to verify code', 'details': str(e)}, status=500)

@require_POST
def reset_password_with_code(request):
    try:
        data = json.loads(request.body)
        email = data.get('email')
        new_password = data.get('new_password')

        user = User.objects.filter(
            models.Q(email=email) |
            models.Q(username=email) |
            models.Q(secondary_identifier=email)
        ).first()

        if not user:
            return JsonResponse({'error': 'No account found with this email'}, status=400)

        user.set_password(new_password)
        user.save()

        return JsonResponse({'status': 'success', 'message': 'Password reset successfully'})
    except Exception as e:
        print(f"Error in reset_password_with_code: {str(e)}")
        return JsonResponse({'error': 'Failed to reset password', 'details': str(e)}, status=500)

@require_POST
def reset_password_with_wallet(request):
    try:
        data = json.loads(request.body)
        email = data.get('email')
        new_password = data.get('new_password')

        user = User.objects.filter(
            models.Q(email=email) |
            models.Q(username=email) |
            models.Q(secondary_identifier=email)
        ).first()

        # Updated for multiple wallets support - use primary wallet
        if not user:
            return JsonResponse({'error': 'No account found with this email'}, status=400)

        primary_wallet = WalletProfile.get_primary_wallet(user)
        if not primary_wallet:
            return JsonResponse({'error': 'No wallet linked to this account'}, status=400)

        public_key = primary_wallet.public_key
        signed_message_base64 = request.session.get('signed_message')
        if not signed_message_base64:
            return JsonResponse({'error': 'Signed message not found in session'}, status=400)

        signed_message = base64.b64decode(signed_message_base64)
        original_message = f"Sign this message to reset your password. Wallet: {public_key}".encode('utf-8')

        if not verify_signed_message(public_key, signed_message, original_message):
            return JsonResponse({'error': 'Signature verification failed'}, status=400)

        request.session.pop('signed_message', None)

        user.set_password(new_password)
        user.save()

        return JsonResponse({'status': 'success', 'message': 'Password reset successfully'})
    except Exception as e:
        print(f"Error in reset_password_with_wallet: {str(e)}")
        return JsonResponse({'error': 'Failed to reset password', 'details': str(e)}, status=500)
    

@require_GET
@login_required
def get_unread_notifications_count(request):
    try:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        return JsonResponse({'status': 'success', 'unread_count': unread_count})
    except Exception as e:
        print(f"Error in get_unread_notifications_count: {str(e)}")
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)



