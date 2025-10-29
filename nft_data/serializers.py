# nft_data/serializers.py

from rest_framework import serializers
from .models import NFTCollection, NFT
# CORRECTED: Import the analytics model to use its data.
from analytics.models import AggregatedCollectionStats

class NFTSerializer(serializers.ModelSerializer):
    """Serializes core data for a single NFT."""
    class Meta:
        model = NFT
        fields = ['mint_address', 'name', 'image_url', 'traits', 'collection']

class NFTCollectionSerializer(serializers.ModelSerializer):
    """
    Serializes core collection data and links to its aggregated analytics.
    """
    # Use a nested serializer or method fields to pull in the analytics data.
    stats = serializers.SerializerMethodField()

    class Meta:
        model = NFTCollection
        fields = ['address', 'name', 'display_name', 'image_url', 'description', 'stats']

    def get_stats(self, obj: NFTCollection) -> dict:
        """
        Fetches the aggregated analytics data for this collection.
        
        This correctly gets data from the related AggregatedCollectionStats object,
        keeping the serializer decoupled from the raw indexer data.
        """
        # The 'aggregated_stats' is the `related_name` from the OneToOneField
        # in the analytics.AggregatedCollectionStats model.
        try:
            stats_obj = obj.aggregated_stats
            return {
                "floor_price": stats_obj.floor_price,
                "volume_24h": stats_obj.volume_24h,
                "total_supply": stats_obj.total_supply,
                "performance_score": stats_obj.performance_score,
                "updated_at": stats_obj.updated_at,
            }
        except AggregatedCollectionStats.DoesNotExist:
            return None