# wallet/adapters.py
from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.urls import reverse

class CustomAccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        print(f"CustomAccountAdapter: User authenticated: {request.user.is_authenticated}, Staff: {request.user.is_staff if request.user.is_authenticated else 'N/A'}")
        if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
            print("CustomAccountAdapter: Redirecting to admin:index")
            return reverse('admin:index')
        print("CustomAccountAdapter: Redirecting to homepage")
        return '/'

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def get_login_redirect_url(self, request):
        print(f"CustomSocialAccountAdapter: User authenticated: {request.user.is_authenticated}, Staff: {request.user.is_staff if request.user.is_authenticated else 'N/A'}")
        if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
            print("CustomSocialAccountAdapter: Redirecting to admin:index")
            return reverse('admin:index')
        print("CustomSocialAccountAdapter: Redirecting to homepage")
        return '/'

    def pre_social_login(self, request, sociallogin):
        print(f"CustomSocialAccountAdapter: Pre-social login, user exists: {sociallogin.is_existing}")
        if not sociallogin.is_existing:
            request.session['google_signup_data'] = {
                'google_id': sociallogin.account.uid,
                'email': sociallogin.account.extra_data.get('email', ''),
                'first_name': sociallogin.account.extra_data.get('given_name', ''),
                'last_name': sociallogin.account.extra_data.get('family_name', '')
            }
        super().pre_social_login(request, sociallogin)