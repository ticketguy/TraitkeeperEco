# api/urls.py
from django.urls import path
from traitkeeper import views
from . import views as api_views

urlpatterns = [
    path('solana-network-stats/', views.solana_network_stats, name='solana_network_stats'),
    path('nft-details/<str:mint_address>/', views.get_nft_details_api, name='get_nft_details_api'),
    path('search-collections/', api_views.search_collections, name='search_collections'),
]