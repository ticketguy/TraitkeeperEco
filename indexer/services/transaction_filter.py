# indexer/services/transaction_filter.py
import logging
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

class TransactionFilter:
    """
    Determines which transactions are useful for marketplace tracking.
    
    Philosophy:
    - Track: Sales, listings, bids, transfers (marketplace activity)
    - Skip: Admin operations, pool management, system operations
    """
    
    # Event types we care about for marketplace tracking
    TRACKABLE_EVENTS = {
        'SALE',
        'LISTING', 
        'CANCEL_LISTING',
        'BID',
        'BID_CANCELLED',
        'TRANSFER',  # Optional - tracks ownership changes
    }
    
    # Event types we should ignore (not useful for marketplace)
    IGNORABLE_EVENTS = {
        'POOL_DEPOSIT',
        'POOL_WITHDRAW',
        'POOL_CREATE',
        'POOL_UPDATE',
        'ADMIN_OPERATION',
        'ESCROW_OPERATION',
        'COMPUTE_BUDGET',
        'SYSTEM_OPERATION',
    }
    
    # Instruction actions that indicate admin operations (should skip)
    ADMIN_ACTIONS = {
        'create_pool',
        'create_pool_v2',
        'update_pool',
        'update_pool_v2',
        'set_shared_escrow',
        'set_shared_escrow_v2',
        'update_allowlists',
        'update_allowlists_v2',
        'update_auction_house',
        'update_auction_house_v2',
        'initialize',
        'close',
    }
    
    # Program IDs we always skip (system programs)
    SYSTEM_PROGRAMS = {
        'ComputeBudget111111111111111111111111111111',  # Compute Budget
        '11111111111111111111111111111111',  # System Program
        'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA',  # Token Program (unless NFT involved)
    }
    

    # Known marketplace programs we want to track
    MARKETPLACE_PROGRAMS = {
        # Magic Eden
        'mmm3XBJg5gk8XJxEKBvdgptZz6SgK4tXvn36sodowMc',  # ME MMM
        'M2mx93ekt1fmXSVkTrUL9xVFHkmME8HTUi5Cyc5aF7K',   # ME V2
        
        # Tensor
        'TCMPhJdwDryooaGtiocG1u3xcYbRpiJzb283XfCZsDp',   # Tensor cNFT
        'TSWAPaqyCSx2KABk68Shruf4rp7CxcNi8hAsbdwmHbN',  # Tensor AMM
        'TSwAPtR1njUk1Ms5T7KBB1BPfiGCu4Qg3jMK6yKgUAJ',  # Tensor Escrow
        
        # Add more marketplaces as you discover them
    }


    def __init__(self):
        logger.info("TransactionFilter initialized")
    
    def should_skip_by_action(self, marketplace: str, action: str) -> bool:
        """
        Check if we should skip based on marketplace action.
        
        Args:
            marketplace: e.g., 'magic_eden_mmm'
            action: e.g., 'update_pool'
            
        Returns:
            True if should skip, False if should process
        """
        if action in self.ADMIN_ACTIONS:
            logger.debug(f"Skipping admin action: {marketplace}/{action}")
            return True
        return False
    
    def should_skip_by_event_type(self, event_type: str) -> bool:
        """
        Check if we should skip based on inferred event type.
        
        Args:
            event_type: e.g., 'POOL_DEPOSIT', 'SALE'
            
        Returns:
            True if should skip, False if should process
        """
        if event_type in self.IGNORABLE_EVENTS:
            logger.debug(f"Skipping ignorable event type: {event_type}")
            return True
        
        if event_type not in self.TRACKABLE_EVENTS:
            logger.debug(f"Event type '{event_type}' not in trackable list")
            return False  # Let it through for now, Tier 3 will decide
        
        return False
    
    def should_skip_by_program(self, program_id: str) -> bool:
        """Check if we should skip based on program ID."""
        if program_id in self.SYSTEM_PROGRAMS:
            logger.debug(f"Skipping system program: {program_id}")
            return True
        return False
    
    def analyze_transaction_value(self, tx_data: dict) -> Dict:
        """
        Analyze if a transaction has marketplace value.
        
        Returns dict with:
        - is_valuable: bool
        - reason: str (why valuable or not)
        - confidence: float (0-1)
        - suggested_action: 'process' | 'skip' | 'review'
        """
        result = {
            'is_valuable': False,
            'reason': '',
            'confidence': 0.0,
            'suggested_action': 'skip'
        }
        
        # Check 1: Has NFT transfer? (High value indicator)
        token_transfers = tx_data.get('tokenTransfers', [])
        nft_transfers = [
            t for t in token_transfers 
            if t.get('tokenStandard') in ['NonFungible', 'NonFungibleEdition']
        ]
        
        if nft_transfers:
            result['is_valuable'] = True
            result['confidence'] = 0.9
            result['suggested_action'] = 'process'
            
            # Check for payment to determine if sale or just transfer
            native_transfers = tx_data.get('nativeTransfers', [])
            large_payments = [
                t for t in native_transfers 
                if t.get('amount', 0) > 10_000_000  # > 0.01 SOL
            ]
            
            if large_payments:
                result['reason'] = 'NFT sale transaction (has transfer + payment)'
                result['confidence'] = 0.95
            else:
                result['reason'] = 'NFT movement transaction (transfer without large payment)'
                result['confidence'] = 0.8
                # Could be listing, delisting, or simple transfer
            
            return result
        
        # Check 2: Has marketplace instruction but no NFT transfer
        # This could be listing/delisting/bidding
        instructions = tx_data.get('instructions', [])
        marketplace_programs = [
            'mmm3XBJg5gk8XJxEKBvdgptZz6SgK4tXvn36sodowMc',  # ME MMM
            'M2mx93ekt1fmXSVkTrUL9xVFHkmME8HTUi5Cyc5aF7K',   # ME V2
            'TCMPhJdwDryooaGtiocG1u3xcYbRpiJzb283XfCZsDp',   # Tensor cNFT
            'TSWAPaqyCSx2KABk68Shruf4rp7CxcNi8hAsbdwmHbN',  # Tensor AMM
        ]
        
        has_marketplace_ix = any(
            ix.get('programId') in marketplace_programs 
            for ix in instructions
        )
        
        if has_marketplace_ix:
            # Could be listing/bid/etc
            result['is_valuable'] = True
            result['reason'] = 'Marketplace instruction (listing/bid/cancel)'
            result['confidence'] = 0.7
            result['suggested_action'] = 'process'
            return result
        
        # Check 3: Nothing valuable
        result['is_valuable'] = False
        result['reason'] = 'No NFT transfers or marketplace instructions detected'
        result['confidence'] = 0.95
        result['suggested_action'] = 'skip'
        
        return result

    def is_marketplace_program(self, program_id: str) -> bool:
        """
        Check if a program ID belongs to a marketplace we care about.
        
        Returns:
            True if it's a marketplace program (should track)
            False if it's a system program (should skip)
        """
        # Quick check: Is it in our known marketplace list?
        if program_id in self.MARKETPLACE_PROGRAMS:
            logger.debug(f"Program {program_id[:8]}... is a known marketplace")
            return True
        
        # Quick reject: Is it a system program?
        if program_id in self.SYSTEM_PROGRAMS:
            logger.debug(f"Program {program_id[:8]}... is a system program")
            return False
        
        # Unknown program - could be a new marketplace
        # Let it through for analysis
        logger.debug(f"Program {program_id[:8]}... is unknown, allowing for analysis")
        return True