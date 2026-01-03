from django.urls import path
from wallet import views

app_name = 'wallet'

urlpatterns = [
    path('email-signup/', views.email_signup, name='email_signup'),
    path('verify-email-code/', views.verify_email_code, name='verify_email_code'),
    path('email-login/', views.email_login, name='email_login'),
    path('google-signup/', views.google_signup, name='google_signup'),
    path('get-google-signup-data/', views.get_google_signup_data, name='get_google_signup_data'),
    path('session/', views.create_session, name='create_session'),
    path('verify-session/', views.verify_session, name='verify_session'),  # New endpoint
    path('disconnect/', views.disconnect_wallet, name='disconnect_wallet'),
    path('settings/', views.user_profile_settings, name='user_profile_settings'),
    path('link-wallet/', views.link_wallet, name='link_wallet'),
    path('link-google/', views.link_google, name='link_google'),
    path('store-signed-message/', views.store_signed_message, name='store_signed_message'),
    path('initiate-password-reset/', views.initiate_password_reset, name='initiate_password_reset'),
    path('send-password-reset-code/', views.send_password_reset_code, name='send_password_reset_code'),
    path('verify-password-reset-code/', views.verify_password_reset_code, name='verify_password_reset_code'),
    path('reset-password-with-code/', views.reset_password_with_code, name='reset_password_with_code'),
    path('reset-password-with-wallet/', views.reset_password_with_wallet, name='reset_password_with_wallet'),

    path('get-unread-notifications-count/', views.get_unread_notifications_count, name='get_unread_notifications_count'),

    # Custodial wallet export
    path('export/<int:wallet_id>/', views.export_wallet_view, name='export_wallet'),
]