# profiles/urls.py
from django.urls import path
from . import views

app_name = 'profiles'  # Namespace for URLs

urlpatterns = [
    # Profile view
    path('<str:username>/', views.profile_view, name='profile'),

    # Settings router (redirects to profile settings by default)
    path('settings/', views.settings_view_router, name='settings'),

    # Settings sections - GET for display
    path('settings/profile/', views.settings_profile_view, name='settings_profile'),
    path('settings/wallets/', views.settings_wallets_view, name='settings_wallets'),
    path('settings/notifications/', views.settings_notifications_view, name='settings_notifications'),
    path('settings/visibility/', views.settings_visibility_view, name='settings_visibility'),
    path('settings/account/', views.settings_account_view, name='settings_account'),

    # Settings actions - POST handlers (template expects these URLs)
    path('settings/update-profile/', views.settings_profile_view, name='update_profile'),
    path('settings/update-notifications/', views.settings_notifications_view, name='update_notifications'),
    path('settings/update-visibility/', views.settings_visibility_view, name='update_visibility'),

    # Wallet actions
    path('settings/remove-wallet/<int:wallet_id>/', views.remove_wallet_view, name='remove_wallet'),
    path('settings/set-primary-wallet/<int:wallet_id>/', views.set_primary_wallet_view, name='set_primary_wallet'),

    # Account deletion
    path('settings/account/delete/', views.delete_account_view, name='delete_account'),

    # Watchlist actions
    path('watchlist/add/', views.add_to_watchlist, name='add_to_watchlist'),
    path('watchlist/remove/<int:watchlist_id>/', views.remove_from_watchlist, name='remove_from_watchlist'),
    path('watchlist/update-notes/<int:watchlist_id>/', views.update_watchlist_notes, name='update_watchlist_notes'),

    # Quest pages and actions
    path('quests/', views.quests_page_view, name='quests'),
    path('quests/<int:quest_id>/claim/', views.quest_claim_view, name='quest_claim'),
    path('quests/claim/confirm/', views.quest_claim_confirm_view, name='quest_claim_confirm'),

    # Quest & Achievement API endpoints
    path('api/quests/', views.api_quests_list, name='api_quests_list'),
    path('api/quests/<int:quest_id>/progress/', views.api_quest_progress, name='api_quest_progress'),
    path('api/achievements/', views.api_achievements_list, name='api_achievements_list'),
    path('api/achievements/<str:username>/', views.api_achievements_list, name='api_achievements_user'),
]