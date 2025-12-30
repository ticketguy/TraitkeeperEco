"""
URL patterns for the TraitKeeper admin panel, mapping routes to views for authentication,
NFT data management, statistics, and API endpoints for dashboard charts.
"""

from django.urls import path, include
from . import views
from traitkeeper.admin_site import admin_site

app_name = 'admin_panel'

urlpatterns = [
    # Authentication URLs
    path('login/', views.login_view, name='login'),
    path('logout/', views.admin_logout, name='logout'),
    path('password-reset/', views.password_reset_request, name='password_reset'),
    path('password-reset-confirm/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),

    # Admin User Management URLs
    path('select-admin-user/', views.select_admin_user, name='select_admin_user'),

    # Statistics URLs
    path('statistics/', views.statistics, name='statistics'),
    path('statistics/export/', views.export_statistics, name='export_statistics'),

    # NFT Data Management URLs
    path('nft_data/', views.nft_data_models, name='nft_data_models'),
    path('nft-data/collections/', views.nft_collections, name='nft_collections'),
    path('nft-data/collections/<str:collection_address>/', views.nft_collection_detail, name='nft_collection_detail'),
    path('nft-data/trait-types/', views.trait_types, name='trait_types'),
    path('nft-data/trait-types/<int:trait_type_id>/', views.trait_values, name='trait_values'),
    path('nft-data/pending-collections/', views.pending_collections, name='pending_collections'),
    path('nft-collection-action/<str:address>/<str:action>/', views.nft_collection_action, name='nft_collection_action'),  # Added for NFTCollection actions
    path('nft-data/transactions/', views.nft_transactions, name='nft_transactions'),

    # API Endpoints for Dashboard Charts
    path('api/user-activity/', views.user_activity_data, name='user_activity_data'),
    path('api/nft-stats/', views.nft_stats_data, name='nft_stats_data'),
    path('api/user-stats/', views.user_stats_data, name='user_stats_data'),
    path('api/signup-activity/', views.signup_activity_data, name='signup_activity_data'),

    # New task management endpoints
    path('task-dashboard/', views.task_dashboard, name='task-dashboard'),

    path('task-manager/status/', views.task_manager_status, name='task-manager-status'),
    path('task-manager/trigger-indexing/', views.trigger_collection_indexing, name='trigger-indexing'),
    path('task-manager/trigger-stats/', views.trigger_stats_update, name='trigger-stats'),
    path('task-manager/history/', views.task_history, name='task-history'),
    path('task-manager/restart/', views.restart_task_manager, name='restart-task-manager'),

    # Secrets Management
    path('secrets/', views.secrets_management, name='secrets-management'),

    # Provider Management - Secure path
    path('rpc-config-panel-7f9a2e8c/', views.provider_management, name='provider-management'),
    path('api/rpc-config-7f9a2e8c/status/', views.provider_status_api, name='provider-status-api'),
    path('api/rpc-config-7f9a2e8c/<int:provider_id>/set-primary/', views.provider_set_primary_api, name='provider-set-primary'),
    path('api/rpc-config-7f9a2e8c/<int:provider_id>/toggle-active/', views.provider_toggle_active_api, name='provider-toggle-active'),
    path('api/rpc-config-7f9a2e8c/<int:provider_id>/update-tier/', views.provider_update_tier_api, name='provider-update-tier'),

    # Role & Permission Management (RBAC)
    path('roles/', views.role_list, name='role-list'),
    path('roles/create/', views.role_create, name='role-create'),
    path('roles/<int:role_id>/edit/', views.role_edit, name='role-edit'),
    path('roles/<int:role_id>/delete/', views.role_delete, name='role-delete'),
    path('users/role-management/', views.user_role_management, name='user-role-management'),
    path('users/<int:user_id>/assign-role/', views.user_assign_role, name='user-assign-role'),
    path('roles/permission-matrix/', views.permission_matrix, name='permission-matrix'),

    # User Profile
    path('profile/', views.user_profile, name='user-profile'),
]