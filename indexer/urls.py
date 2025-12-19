# indexer/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Webhook endpoint for Helius and QuickNode streams
    path('webhook/', views.webhook_handler, name='webhook_handler'),
]