# indexer/urls.py
from django.urls import path
from . import views
"""
urlpatterns = [
    path('collection-stats/<str:collection_address>/', views.CollectionMarketStatsView.as_view(), name='collection-stats'),
    path('nft-events/', views.NFTEventView.as_view(), name='nft-events'),
    path('trait-events/', views.TraitEventView.as_view(), name='trait-events'),
    path('collections/', views.NFTCollectionView.as_view(), name='collections'),
    path('trait-types/', views.TraitTypeView.as_view(), name='trait-types'),
    path('trait-values/', views.TraitValueView.as_view(), name='trait-values'),
    path('trait-filtered-events/<str:collection_address>/', views.TraitFilteredEventView.as_view(), name='trait-filtered-events'),
    path('trait-performance/', views.TraitPerformanceView.as_view(), name='trait-performance'),
    path('trending-traits/', views.TrendingTraitsView.as_view(), name='trending-traits'),
    path('top-traits/', views.TopTraitsView.as_view(), name='top-traits'),
    path('high-profile-transfers/', views.HighProfileTransfersView.as_view(), name='high-profile-transfers'),
    path('collection-sweeps/', views.CollectionSweepsView.as_view(), name='collection-sweeps'),
    path('wallet-prominence/', views.WalletProminenceView.as_view(), name='wallet-prominence'),
    path('wallet-events/', views.WalletEventView.as_view(), name='wallet-events'),
    path('failed-transactions/', views.FailedTransactionView.as_view(), name='failed-transactions'),
    path('dynamic-nft-events/', views.DynamicNFTEventView.as_view(), name='dynamic-nft-events'),
    path('batch-events/', views.BatchEventView.as_view(), name='batch-events'),
    path('historical-trends/', views.HistoricalTrendView.as_view(), name='historical-trends'),
    path('trait-analytics/', views.TraitAnalyticsView.as_view(), name='trait-analytics'),
    path('rarity-filtered-events/', views.RarityFilteredEventView.as_view(), name='rarity-filtered-events'),
    path('cross-collection-comparison/', views.CrossCollectionComparisonView.as_view(), name='cross-collection-comparison'),
    path('event-forecast/', views.EventForecastView.as_view(), name='event-forecast'),
    path('webhook/', views.webhook_handler, name='webhook_handler'),  # Webhook endpoint for Helius events
]

"""