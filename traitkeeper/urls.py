"""
URL configuration for traitkeeper project.
"""

from .admin_site import admin_site
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from . import views
from nft_data.views import submit_collection

urlpatterns = [
    # Health check endpoint for Docker
    path('health/', views.health_check, name='health_check'),

    # Admin page
    path('admin/', admin_site.urls),

    # Landing page
    path('', views.index, name='index'),
    # SSE Endpoints
    path('stream-site-updates/', views.stream_site_updates, name='stream_site_updates'),
    path('stream-hero-slides/', views.stream_hero_slides, name='stream_hero_slides'),
    path('stream-highest-vitality-collections/', views.stream_highest_vitality_collections, name='stream_highest_vitality_collections'),


    # Collection detail page
    path('collection/<str:address>/', views.collection_detail, name='collection_detail'),
    # URL for the NFT Detail API
    path('api/get-nft-details/<str:mint_address>/', views.get_nft_details_api, name='api_get_nft_details'),

    # Admin panel URLs
    path('admin-panel/', include('admin_panel.urls')),
    # Wallet URLs
    path('wallet/', include('wallet.urls')),
    # Profiles URLs
    path('profile/', include('profiles.urls', namespace='profiles')),
    # Site pages or apps URLs
    path('nftmemories', include('nftmemories.urls')),
    path('nft-data/', include('nft_data.urls')),
   # path('indexer/', include('indexer.urls')),


    path('marketplace/', include('marketplace.urls')),

    path('system-health/', include('system_health.urls')),

    # Admin Secure URLs (encrypted secrets management)
    path('admin-secure/', include('admin_secure.urls'))Human: continue

    # API URLs
    path('api/', include('traitkeeper.api.urls')),  

    # Notifications URLs
    path('notifications/', include('notifications.urls')),
    path('accounts/', include('allauth.urls')),
    # Collection submission
    path('submit-collection/', submit_collection, name='submit_collection'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
