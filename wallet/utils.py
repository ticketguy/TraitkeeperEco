import base58
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect
from functools import wraps
from django.urls import reverse
import nacl.signing

def wallet_connected_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not (request.user.is_authenticated and hasattr(request.user, 'walletprofile') and request.user.walletprofile.is_connected):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'redirect': reverse('register_nft:index')})
            return redirect('register_nft:index')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def verify_signed_message(public_key, signed_message, original_message):
    try:
        # Convert the public key from base58 to bytes
        public_key_bytes = base58.b58decode(public_key)
        
        # Create a VerifyKey object from the public key bytes
        verify_key = nacl.signing.VerifyKey(public_key_bytes)
        
        # Verify the signature against the original message
        # PyNaCl expects the signature (64 bytes) and the original message
        verify_key.verify(original_message, signed_message)
        
        return True
    except Exception as e:
        print(f"Error verifying signature: {str(e)}")
        return False