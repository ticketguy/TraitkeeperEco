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
    collection_address = serializers.CharField(source='collection.address', read_only=True)

    class Meta:
        model = CollectionMarketStats
        fields = ['collection_address', 'source', 'floor_price', 'volume_24h', 'sales_count_24h', 'owners_count', 'listed_count', 'total_supply', 'timestamp']

