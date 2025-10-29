# api/urls.py
from django.urls import path
from traitkeeper import views

urlpatterns = [
    path('solana-network-stats/', views.solana_network_stats, name='solana_network_stats'),
    path('nft-details/<str:mint_address>/', views.get_nft_details_api, name='get_nft_details_api'),

]