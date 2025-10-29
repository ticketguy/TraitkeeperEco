# nft_memories/urls.py

from django.urls import path
from .views import CollectionMemoriesView, EventDetailView, ModerateBurnReasonsView

urlpatterns = [
    path('collection/<str:collection_address>/memories/', CollectionMemoriesView.as_view(), name='collection-memories'),
    path('collection/<str:collection_address>/event/<str:event_id>/', EventDetailView.as_view(), name='event_detail'),
    path('moderate-burn-reasons/', ModerateBurnReasonsView.as_view(), name='moderate_burn_reasons'),
]