# marketplace/urls.py
from django.urls import path
from . import views


app_name = 'marketplace'

urlpatterns = [
    # --- Direct Sell (Fixed Price, Non-Negotiable) ---
    path('api/direct-sell/set/', views.api_set_direct_sell, name='api_set_direct_sell'),
    path('api/direct-sell/remove/', views.api_remove_direct_sell, name='api_remove_direct_sell'),
    path('api/direct-sell/buy/', views.api_buy_direct_sell, name='api_buy_direct_sell'),

    # --- Sell Intent (Asking Price + Negotiable) ---
    path('api/sell-intent/set/', views.api_set_sell_intent, name='api_set_sell_intent'),
    path('api/sell-intent/remove/', views.api_remove_sell_intent, name='api_remove_sell_intent'),
    path('api/sell-intent/accept/', views.api_accept_asking_price, name='api_accept_asking_price'),

    # --- Private Bidding Actions (Unsolicited Offers) ---
    path('api/bid/place/', views.api_place_bid, name='api_place_bid'),
    path('api/bid/accept/', views.api_accept_bid, name='api_accept_bid'),
    path('api/bid/reject/', views.api_reject_bid, name='api_reject_reject'),
    path('api/bid/cancel/', views.api_cancel_bid, name='api_cancel_bid'),
    path('api/get-nft-offers/<str:nft_mint>/', views.api_get_nft_offers, name='api_get_nft_offers'),
    path('api/bid/confirm/', views.api_confirm_bid, name='api_confirm_bid'),

    # --- Counter Offers ---
    path('api/bid/counter/', views.api_owner_counter_bid, name='api_owner_counter_bid'), 
    path('api/sell-intent/counter/', views.api_bidder_counter_sell_intent, name='api_bidder_counter_sell_intent'),

    # --- Auction Actions ---
    path('api/auction/create/', views.api_create_auction, name='api_create_auction'),
    path('api/auction/bid/', views.api_place_auction_bid, name='api_place_auction_bid'),
    path('api/auction/cancel/', views.api_cancel_auction, name='api_cancel_auction'),
    path('api/auction/finalize/', views.api_finalize_auction, name='api_finalize_auction'),

    # --- Parallel Lines Integration (World Perception Engine) ---
    path('api/perception/webhook', views.api_parallel_lines_webhook, name='api_parallel_lines_webhook'),

]