# indexer/services/discriminator_learner.py
import logging
from typing import Optional, Dict, Tuple
from asgiref.sync import sync_to_async
from ..models import UnknownDiscriminator
from ..nft_constants import get_marketplace_from_program_id
from django.utils import timezone

logger = logging.getLogger(__name__)

class DiscriminatorLearner:
    """
    Auto-discovers and learns new instruction discriminators.
    
    When an unknown discriminator is encountered, this service:
    1. Analyzes the transaction to infer what it does
    2. Logs it to the database for review
    3. Can auto-add common patterns
    """
    
    def __init__(self):
        self.confidence_threshold = 0.8  # Auto-approve if confidence >= 80%
    
    async def handle_unknown_discriminator(
        self, 
        program_id: str, 
        discriminator: bytes,
        tx_data: dict,
        signature: str
    ) -> Optional[Tuple[str, str]]:
        """
        Handle an unknown discriminator with smart filtering.
        
        Only saves to DB if:
        1. Program is a marketplace (not system program)
        2. Transaction shows value signals (NFT/payment)
        """
        disc_hex = discriminator.hex()
        
        # === LEVEL 1 FILTER: Check if marketplace program ===
        from .transaction_filter import TransactionFilter
        tx_filter = TransactionFilter()
        
        if not tx_filter.is_marketplace_program(program_id):
            logger.debug(f"Skipping system program discriminator: {program_id[:8]}.../{disc_hex}")
            return None  # Don't save, don't analyze
        
        logger.info(f"🔍 Unknown marketplace discriminator: {program_id[:8]}.../{disc_hex}")
        
        # === LEVEL 2 FILTER: Analyze transaction value ===
        analysis = self._analyze_transaction(tx_data)
        
        # Check if transaction has any value signals
        has_value_signals = (
            analysis['has_nft_transfer'] or 
            analysis['has_large_payment'] or
            len(analysis['log_patterns']) > 0
        )
        
        if not has_value_signals:
            logger.debug(f"Skipping valueless discriminator: {disc_hex} (no NFT, payment, or log patterns)")
            return None  # Don't save, not interesting
        
        # === PASSED BOTH FILTERS: Save to database ===
        marketplace = get_marketplace_from_program_id(program_id)
        inferred_action = self._infer_action(analysis)
        
        await self._save_discovery(
            program_id=program_id,
            discriminator=disc_hex,
            marketplace=marketplace,
            action=inferred_action,
            analysis=analysis,
            signature=signature
        )
        
        # Auto-approve if confidence is high
        if analysis['confidence'] >= self.confidence_threshold:
            logger.info(f"✅ Auto-approved: {marketplace}/{inferred_action} (confidence: {analysis['confidence']})")
            return (marketplace, inferred_action)
        
        logger.info(f"⚠️ Needs review: {marketplace}/{inferred_action} (confidence: {analysis['confidence']})")
        return None
    
    def _analyze_transaction(self, tx_data: dict) -> Dict:
        """Analyze transaction to understand what happened."""
        analysis = {
            'has_nft_transfer': False,
            'has_native_transfer': False,
            'has_large_payment': False,
            'log_patterns': [],
            'transfer_count': 0,
            'confidence': 0.0
        }
        
        # Check for NFT transfers
        token_transfers = tx_data.get('tokenTransfers', [])
        nft_transfers = [
            t for t in token_transfers 
            if t.get('tokenStandard') in ['NonFungible', 'NonFungibleEdition']
        ]
        
        if nft_transfers:
            analysis['has_nft_transfer'] = True
            analysis['transfer_count'] = len(nft_transfers)
        
        # Check for significant SOL payments
        native_transfers = tx_data.get('nativeTransfers', [])
        large_payments = [
            t for t in native_transfers 
            if t.get('amount', 0) > 10_000_000  # > 0.01 SOL
        ]
        
        if large_payments:
            analysis['has_native_transfer'] = True
            analysis['has_large_payment'] = True
        
        # Extract log patterns
        logs = tx_data.get('logMessages', [])
        for log in logs:
            log_lower = log.lower()
            # Look for instruction names in logs
            if 'instruction:' in log_lower:
                pattern = log_lower.split('instruction:')[1].strip().split()[0]
                analysis['log_patterns'].append(pattern)
        
        return analysis
    
    def _infer_action(self, analysis: Dict) -> str:
        """Infer what action this instruction performs based on analysis."""
        
        # Pattern 1: Has NFT transfer + large payment = SALE
        if analysis['has_nft_transfer'] and analysis['has_large_payment']:
            analysis['confidence'] = 0.85
            return 'fulfill_sell'
        
        # Pattern 2: Has NFT transfer, no payment = WITHDRAW/DEPOSIT
        if analysis['has_nft_transfer'] and not analysis['has_large_payment']:
            analysis['confidence'] = 0.75
            for pattern in analysis['log_patterns']:
                if 'withdraw' in pattern:
                    analysis['confidence'] = 0.9
                    return 'withdraw_sell'
                if 'deposit' in pattern:
                    analysis['confidence'] = 0.9
                    return 'deposit_sell'
            return 'withdraw_sell'
        
        # ✅ NEW Pattern 3: Check logs FIRST for listing/selling keywords
        if analysis['log_patterns']:
            first_pattern = analysis['log_patterns'][0].lower()
            
            # LISTING operations (no NFT transfer, but valuable!)
            if any(keyword in first_pattern for keyword in ['sell', 'list', 'listing', 'mip1sell']):
                analysis['confidence'] = 0.85
                return 'mip1_sell'  # or 'listing'
            
            # BID operations
            if 'bid' in first_pattern:
                analysis['confidence'] = 0.85
                return 'bid'
            
            # CANCEL operations
            if 'cancel' in first_pattern:
                analysis['confidence'] = 0.85
                return 'cancel'
            
            # UPDATE operations (admin)
            if 'update' in first_pattern:
                analysis['confidence'] = 0.95
                return 'update_pool'
            
            # CREATE operations (admin)
            if 'create' in first_pattern:
                analysis['confidence'] = 0.95
                return 'create_pool'
            
            # ESCROW operations (admin)
            if 'escrow' in first_pattern:
                analysis['confidence'] = 0.95
                return 'set_shared_escrow'
        
        # Pattern 4: No transfers AND no recognizable logs = admin operation
        if not analysis['has_nft_transfer'] and not analysis['has_large_payment']:
            analysis['confidence'] = 0.9
            return 'admin_operation'
        
        # Unknown
        analysis['confidence'] = 0.3
        return 'unknown'
    
    async def _save_discovery(
        self,
        program_id: str,
        discriminator: str,
        marketplace: str,
        action: str,
        analysis: Dict,
        signature: str
    ):
        """Save or update the discovered discriminator."""
        try:
            ignore_actions = [
            'admin_operation', 
            'update_pool', 
            'create_pool', 
            'set_shared_escrow',
            'unknown'
        ]
            unknown, created = await sync_to_async(
                UnknownDiscriminator.objects.get_or_create
            )(
                program_id=program_id,
                discriminator=discriminator,
                defaults={
                    'inferred_marketplace': marketplace,
                    'inferred_action': action,
                    'has_nft_transfer': analysis['has_nft_transfer'],
                    'has_native_transfer': analysis['has_native_transfer'],
                    'log_patterns': analysis['log_patterns'],
                    'sample_signatures': [signature],
                    'occurrence_count': 1,
                    'should_ignore': action in ignore_actions 
                }
            )
            
            if not created:
                # Update existing record
                unknown.occurrence_count += 1
                unknown.last_seen = timezone.now()
                
                # Add signature to samples (max 5)
                if signature not in unknown.sample_signatures:
                    unknown.sample_signatures.append(signature)
                    if len(unknown.sample_signatures) > 5:
                        unknown.sample_signatures = unknown.sample_signatures[-5:]
                
                await sync_to_async(unknown.save)()
                logger.debug(f"Updated unknown discriminator (seen {unknown.occurrence_count} times)")
            else:
                logger.info(f"🆕 New unknown discriminator saved: {program_id[:8]}.../{discriminator}")
        
        except Exception as e:
            logger.error(f"Failed to save unknown discriminator: {e}")