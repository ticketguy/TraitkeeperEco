# indexer/serializers.py (new file)
from rest_framework import serializers
from .models import NFTEvent, CollectionMarketStats

class NFTEventSerializer(serializers.ModelSerializer):
    traits = serializers.SerializerMethodField()

    class Meta:
        model = NFTEvent
        fields = ['event_id', 'event_type', 'mint_address', 'amount', 'buyer', 'seller', 'timestamp', 'collection_address', 'marketplace', 'traits']

    def get_traits(self, obj):
        return [{'type': tv.trait_type.name, 'value': tv.value} for tv in obj.trait_values.all()]

class CollectionMarketStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CollectionMarketStats
        fields = ['collection_address', 'floor_price', 'volume_24h', 'average_price_24h', 'velocity_24h', 'performance_score', 'total_volume', 'total_supply', 'listed_count', 'timestamp']

