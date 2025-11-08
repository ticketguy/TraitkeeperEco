# marketplace/perception_service.py

"""
Parallel Lines Integration Service

This service handles:
1. Receiving webhook data from Parallel Lines
2. Validating and storing perception data
3. Providing clean interfaces for vitality calculations
4. Fallback logic when Parallel Lines data is unavailable
"""

import logging
import hashlib
import hmac
from datetime import timedelta
from typing import Optional, Dict, Any, Tuple
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache
from asgiref.sync import sync_to_async

from nft_data.models import NFT, NFTCollection, TraitValue
from .perception_models import (
    PerceptionSnapshot,
    PerceptionGraphNode,
    PerceptionGraphEdge,
    PerceptionAggregation,
    ParallelLinesWebhookLog,
    get_latest_perception_index,
    get_perception_trend
)

logger = logging.getLogger(__name__)


class ParallelLinesIntegrationService:
    """
    Service for integrating with Parallel Lines world perception engine.

    This service manages the flow of perception data from Parallel Lines
    into TraitKeeper's vitality calculation system.
    """

    # === CONFIGURATION ===
    CACHE_TTL_SECONDS = 300  # Cache perception scores for 5 minutes
    PERCEPTION_STALENESS_THRESHOLD_HOURS = 24  # Data older than 24h is stale
    DEFAULT_PERCEPTION_INDEX = 0.5  # Neutral score when no data available

    def __init__(self):
        self.logger = logger

    # =========================================================================
    # WEBHOOK PROCESSING
    # =========================================================================

    async def process_webhook(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        endpoint: str = '/api/perception/webhook'
    ) -> Tuple[bool, str, Optional[PerceptionSnapshot]]:
        """
        Process incoming webhook from Parallel Lines.

        Args:
            payload: JSON payload from webhook
            headers: Request headers (for authentication)
            endpoint: Webhook endpoint path

        Returns:
            Tuple of (success: bool, message: str, snapshot: PerceptionSnapshot or None)
        """
        import time
        start_time = time.time()

        # === AUTHENTICATION ===
        auth_result = await self._authenticate_webhook(payload, headers)
        if not auth_result:
            await self._log_webhook_call(
                endpoint=endpoint,
                headers=headers,
                payload=payload,
                status='AUTH_ERROR',
                error_message='Webhook authentication failed'
            )
            return False, 'Authentication failed', None

        # === VALIDATION ===
        validation_result = self._validate_payload(payload)
        if not validation_result['valid']:
            await self._log_webhook_call(
                endpoint=endpoint,
                headers=headers,
                payload=payload,
                status='VALIDATION_ERROR',
                error_message=validation_result['error']
            )
            return False, validation_result['error'], None

        try:
            # === PARSE PAYLOAD ===
            entity_type = payload.get('entity_type')  # 'collection', 'nft', or 'trait'
            entity_id = payload.get('entity_id')
            perception_data = payload.get('perception_data', {})

            # === RESOLVE ENTITY ===
            entity = await self._resolve_entity(entity_type, entity_id)
            if not entity:
                error_msg = f"Entity not found: {entity_type} {entity_id}"
                await self._log_webhook_call(
                    endpoint=endpoint,
                    headers=headers,
                    payload=payload,
                    status='FAILED',
                    error_message=error_msg
                )
                return False, error_msg, None

            # === CREATE PERCEPTION SNAPSHOT ===
            snapshot = await self._create_perception_snapshot(
                entity_type=entity_type,
                entity=entity,
                perception_data=perception_data,
                source_type='WEBHOOK',
                raw_payload=payload
            )

            # === PROCESS PERCEPTION GRAPH (if included) ===
            if payload.get('perception_graph'):
                await self._process_perception_graph(
                    graph_data=payload['perception_graph'],
                    graph_id=perception_data.get('perception_graph_id')
                )

            # === LOG SUCCESS ===
            processing_time_ms = int((time.time() - start_time) * 1000)
            await self._log_webhook_call(
                endpoint=endpoint,
                headers=headers,
                payload=payload,
                status='SUCCESS',
                snapshots_created=1,
                processing_time_ms=processing_time_ms,
                perception_snapshot=snapshot
            )

            # === INVALIDATE CACHE ===
            await self._invalidate_perception_cache(entity_type, entity)

            self.logger.info(
                f"✅ Perception data received for {entity_type} {entity_id}: "
                f"Index={snapshot.perception_index:.3f}"
            )

            return True, 'Success', snapshot

        except Exception as e:
            error_msg = f"Error processing webhook: {str(e)}"
            self.logger.exception(error_msg)

            await self._log_webhook_call(
                endpoint=endpoint,
                headers=headers,
                payload=payload,
                status='FAILED',
                error_message=error_msg
            )

            return False, error_msg, None

    async def _authenticate_webhook(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> bool:
        """
        Authenticate webhook request from Parallel Lines.

        Supports:
        - HMAC signature verification
        - API key validation
        - IP whitelist (if configured)

        Returns:
            bool: True if authenticated, False otherwise
        """
        # === METHOD 1: HMAC Signature ===
        if hasattr(settings, 'PARALLEL_LINES_WEBHOOK_SECRET'):
            signature = headers.get('X-Parallel-Lines-Signature', '')
            if signature:
                import json
                expected_signature = hmac.new(
                    settings.PARALLEL_LINES_WEBHOOK_SECRET.encode(),
                    json.dumps(payload, sort_keys=True).encode(),
                    hashlib.sha256
                ).hexdigest()

                if hmac.compare_digest(signature, expected_signature):
                    return True
                else:
                    self.logger.warning("HMAC signature mismatch")
                    return False

        # === METHOD 2: API Key ===
        if hasattr(settings, 'PARALLEL_LINES_API_KEY'):
            api_key = headers.get('X-API-Key', '')
            if api_key == settings.PARALLEL_LINES_API_KEY:
                return True

        # === METHOD 3: IP Whitelist ===
        # TODO: Implement if needed

        # === DEVELOPMENT MODE: Allow all (UNSAFE!) ===
        if getattr(settings, 'PARALLEL_LINES_DEV_MODE', False):
            self.logger.warning("⚠️ Parallel Lines webhook auth DISABLED (dev mode)")
            return True

        return False

    def _validate_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate webhook payload structure.

        Returns:
            dict: {'valid': bool, 'error': str or None}
        """
        # Required fields
        required_fields = ['entity_type', 'entity_id', 'perception_data']

        for field in required_fields:
            if field not in payload:
                return {
                    'valid': False,
                    'error': f"Missing required field: {field}"
                }

        # Validate entity_type
        valid_entity_types = ['collection', 'nft', 'trait']
        if payload['entity_type'] not in valid_entity_types:
            return {
                'valid': False,
                'error': f"Invalid entity_type. Must be one of: {valid_entity_types}"
            }

        # Validate perception_data structure
        perception_data = payload.get('perception_data', {})
        if 'perception_index' not in perception_data:
            return {
                'valid': False,
                'error': "perception_data must contain 'perception_index'"
            }

        # Validate perception_index range
        perception_index = perception_data['perception_index']
        if not isinstance(perception_index, (int, float)) or not (0 <= perception_index <= 1):
            return {
                'valid': False,
                'error': "perception_index must be a number between 0 and 1"
            }

        return {'valid': True, 'error': None}

    async def _resolve_entity(
        self,
        entity_type: str,
        entity_id: str
    ) -> Optional[Any]:
        """
        Resolve entity from entity_type and entity_id.

        Args:
            entity_type: 'collection', 'nft', or 'trait'
            entity_id: Identifier (address for collection/nft, ID for trait)

        Returns:
            Entity object or None if not found
        """
        try:
            if entity_type == 'collection':
                return await sync_to_async(NFTCollection.objects.get)(
                    address=entity_id
                )
            elif entity_type == 'nft':
                return await sync_to_async(NFT.objects.get)(
                    mint_address=entity_id
                )
            elif entity_type == 'trait':
                return await sync_to_async(TraitValue.objects.get)(
                    id=entity_id
                )
        except Exception as e:
            self.logger.error(f"Entity resolution failed: {entity_type} {entity_id} - {e}")
            return None

    @transaction.atomic
    async def _create_perception_snapshot(
        self,
        entity_type: str,
        entity: Any,
        perception_data: Dict[str, Any],
        source_type: str = 'WEBHOOK',
        raw_payload: Optional[Dict] = None
    ) -> PerceptionSnapshot:
        """
        Create a PerceptionSnapshot record from perception data.

        Args:
            entity_type: 'collection', 'nft', or 'trait'
            entity: The entity object
            perception_data: Perception metrics from Parallel Lines
            source_type: How this data was received
            raw_payload: Full raw payload for audit

        Returns:
            PerceptionSnapshot instance
        """
        # Build entity field mapping
        entity_field = {entity_type: entity}

        # Extract perception metrics
        snapshot_data = {
            **entity_field,
            'perception_index': perception_data['perception_index'],
            'submind_raw_score': perception_data.get('submind', {}).get('raw_score'),
            'submind_hidden_sentiment': perception_data.get('submind', {}).get('hidden_sentiment'),
            'manipulation_probability': perception_data.get('submind', {}).get('manipulation_probability'),
            'behavioral_pattern_flags': perception_data.get('submind', {}).get('behavioral_patterns', {}),
            'emotional_resonance': perception_data.get('intuone', {}).get('emotional_resonance'),
            'language_tone': perception_data.get('intuone', {}).get('language_tone'),
            'community_awareness_score': perception_data.get('intuone', {}).get('community_awareness'),
            'perception_graph_id': perception_data.get('perception_graph_id'),
            'confidence_score': perception_data.get('confidence', 1.0),
            'data_sources': perception_data.get('data_sources', []),
            'sample_size': perception_data.get('sample_size'),
            'timestamp': timezone.datetime.fromisoformat(perception_data.get('timestamp', timezone.now().isoformat())),
            'source_type': source_type,
            'raw_payload': raw_payload
        }

        snapshot = await sync_to_async(PerceptionSnapshot.objects.create)(
            **snapshot_data
        )

        return snapshot

    async def _process_perception_graph(
        self,
        graph_data: Dict[str, Any],
        graph_id: str
    ) -> None:
        """
        Process and store Perception Graph nodes and edges.

        Args:
            graph_data: Graph structure from Parallel Lines
            graph_id: Unique ID for this graph
        """
        # Process nodes
        for node_data in graph_data.get('nodes', []):
            await sync_to_async(PerceptionGraphNode.objects.update_or_create)(
                graph_id=graph_id,
                node_id=node_data['id'],
                defaults={
                    'node_type': node_data.get('type', 'unknown'),
                    'label': node_data.get('label', ''),
                    'influence_score': node_data.get('influence', 0.0),
                    'sentiment': node_data.get('sentiment'),
                    'metadata': node_data.get('metadata', {})
                }
            )

        # Process edges
        for edge_data in graph_data.get('edges', []):
            source = await sync_to_async(PerceptionGraphNode.objects.get)(
                graph_id=graph_id,
                node_id=edge_data['source']
            )
            target = await sync_to_async(PerceptionGraphNode.objects.get)(
                graph_id=graph_id,
                node_id=edge_data['target']
            )

            await sync_to_async(PerceptionGraphEdge.objects.create)(
                graph_id=graph_id,
                source_node=source,
                target_node=target,
                edge_type=edge_data.get('type', 'relates_to'),
                weight=edge_data.get('weight', 1.0),
                sentiment=edge_data.get('sentiment'),
                metadata=edge_data.get('metadata', {})
            )

    async def _log_webhook_call(
        self,
        endpoint: str,
        headers: Dict,
        payload: Dict,
        status: str,
        error_message: Optional[str] = None,
        snapshots_created: int = 0,
        processing_time_ms: Optional[int] = None,
        perception_snapshot: Optional[PerceptionSnapshot] = None
    ) -> None:
        """Log webhook call for audit trail."""
        await sync_to_async(ParallelLinesWebhookLog.objects.create)(
            endpoint=endpoint,
            headers=headers,
            payload=payload,
            status=status,
            error_message=error_message,
            snapshots_created=snapshots_created,
            processing_time_ms=processing_time_ms,
            perception_snapshot=perception_snapshot
        )

    async def _invalidate_perception_cache(
        self,
        entity_type: str,
        entity: Any
    ) -> None:
        """Invalidate cached perception scores for an entity."""
        cache_key = self._get_cache_key(entity_type, entity)
        cache.delete(cache_key)

    # =========================================================================
    # PERCEPTION INDEX RETRIEVAL (For Vitality Calculation)
    # =========================================================================

    async def get_perception_index(
        self,
        entity: Any,
        entity_type: str = 'collection',
        use_cache: bool = True
    ) -> float:
        """
        Get the current perception index for an entity.

        This is the primary method called by the vitality calculation service.

        Args:
            entity: NFTCollection, NFT, or TraitValue instance
            entity_type: 'collection', 'nft', or 'trait'
            use_cache: Whether to use cached values

        Returns:
            float: Perception index (0-1)
        """
        # === CHECK CACHE ===
        if use_cache:
            cache_key = self._get_cache_key(entity_type, entity)
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value

        # === GET LATEST SNAPSHOT ===
        filter_kwargs = {entity_type: entity}

        snapshot = await sync_to_async(
            PerceptionSnapshot.objects.filter(**filter_kwargs).order_by('-timestamp').first
        )()

        # === NO DATA AVAILABLE ===
        if not snapshot:
            self.logger.debug(
                f"No perception data available for {entity_type} {entity}. "
                f"Returning default: {self.DEFAULT_PERCEPTION_INDEX}"
            )
            return self.DEFAULT_PERCEPTION_INDEX

        # === CHECK STALENESS ===
        staleness_threshold = timezone.now() - timedelta(
            hours=self.PERCEPTION_STALENESS_THRESHOLD_HOURS
        )

        if snapshot.timestamp < staleness_threshold:
            self.logger.warning(
                f"Perception data for {entity_type} {entity} is stale "
                f"(last updated: {snapshot.timestamp}). Using with caution."
            )
            # Still use stale data, but could implement decay logic here

        perception_index = snapshot.perception_index

        # === ANTI-GAMING ADJUSTMENT ===
        # If high manipulation probability detected, dampen the score
        if snapshot.manipulation_probability and snapshot.manipulation_probability > 0.7:
            self.logger.info(
                f"High manipulation probability ({snapshot.manipulation_probability:.2f}) "
                f"detected for {entity_type} {entity}. Applying dampening."
            )
            # Pull perception towards neutral (0.5) based on manipulation probability
            dampening_factor = snapshot.manipulation_probability * 0.5
            perception_index = perception_index * (1 - dampening_factor) + 0.5 * dampening_factor

        # === CACHE RESULT ===
        if use_cache:
            cache_key = self._get_cache_key(entity_type, entity)
            cache.set(cache_key, perception_index, self.CACHE_TTL_SECONDS)

        return perception_index

    def _get_cache_key(self, entity_type: str, entity: Any) -> str:
        """Generate cache key for perception index."""
        entity_id = getattr(entity, 'address', None) or getattr(entity, 'mint_address', None) or entity.id
        return f"perception_index:{entity_type}:{entity_id}"

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    async def get_perception_trend_async(
        self,
        entity: Any,
        entity_type: str = 'collection',
        days: int = 7
    ) -> Optional[Dict]:
        """
        Get perception trend analysis (async wrapper).

        Returns:
            dict: {'current': float, 'average': float, 'change': float, 'trend': str}
        """
        return await sync_to_async(get_perception_trend)(
            entity=entity,
            entity_type=entity_type,
            days=days
        )

    async def get_perception_history(
        self,
        entity: Any,
        entity_type: str = 'collection',
        days: int = 30,
        limit: int = 100
    ) -> list:
        """
        Get historical perception snapshots.

        Args:
            entity: Entity to get history for
            entity_type: Type of entity
            days: Number of days to look back
            limit: Max number of snapshots to return

        Returns:
            list: List of PerceptionSnapshot objects
        """
        filter_kwargs = {entity_type: entity}
        since = timezone.now() - timedelta(days=days)

        snapshots = await sync_to_async(list)(
            PerceptionSnapshot.objects.filter(
                **filter_kwargs,
                timestamp__gte=since
            ).order_by('-timestamp')[:limit]
        )

        return snapshots


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

# Create a singleton instance for easy importing
perception_service = ParallelLinesIntegrationService()
