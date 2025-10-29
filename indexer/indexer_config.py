# indexer_config.py - Configuration and error handling improvements

import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import json

# Enhanced logging configuration
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
        },
        'simple': {
            'format': '%(levelname)s - %(message)s'
        }
    },
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'indexer.log',
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'detailed',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'indexer_errors.log',
            'maxBytes': 5 * 1024 * 1024,  # 5MB
            'backupCount': 3,
            'formatter': 'detailed',
        }
    },
    'loggers': {
        'indexer': {
            'handlers': ['file', 'console', 'error_file'],
            'level': 'DEBUG',
            'propagate': False
        },
        'helius_provider': {
            'handlers': ['file', 'console', 'error_file'],
            'level': 'DEBUG',
            'propagate': False
        }
    }
}

# Rate limiting configuration
RATE_LIMIT_CONFIG = {
    'magic_eden': {
        'requests_per_minute': 60,
        'burst_limit': 10,
        'backoff_base': 2,
        'max_backoff': 300,  # 5 minutes
    },
    'helius': {
        'requests_per_minute': 100,
        'burst_limit': 20,
        'backoff_base': 1.5,
        'max_backoff': 60,
    },
    'tensor': {
        'requests_per_minute': 120,
        'burst_limit': 15,
        'backoff_base': 2,
        'max_backoff': 180,
    }
}

# Transaction processing configuration
TRANSACTION_CONFIG = {
    'max_retries': 3,
    'retry_delay': 5,  # seconds
    'batch_size': 50,
    'max_concurrent_requests': 10,
    'timeout': 30,  # seconds
}

# NFT Event types that should be processed
VALID_NFT_EVENT_TYPES = {
    'NFT_SALE',
    'NFT_LISTING', 
    'NFT_DELISTING',
    'NFT_BID',
    'NFT_MINT',
    'TRANSFER',
    'COMPRESSED_NFT_MINT',
    'COMPRESSED_NFT_BURN',
}

# Event types to skip (not NFT-related)
SKIP_EVENT_TYPES = {
    'UNKNOWN',
    'NFT_BID_CANCELLED',  # Unless specifically needed
    'SWAP',
    'TRANSFER_SOL', 
    'CREATE_ACCOUNT',
    'CLOSE_ACCOUNT',
    'TOKEN_MINT',  # Unless it's an NFT mint
}

# Known NFT-related program IDs
NFT_PROGRAM_IDS = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",  # Token Program
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",  # Token-2022 Program  
    "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s",   # Metaplex Token Metadata
    "BGUMAp9Gq7iTEuizy4pqaxsTyUCBK68MDfK752saRPUY",  # Bubblegum (Compressed NFTs)
    "CJsLwbP1iu5DuUikHEJnLfANgKy6stB2uFgvBBHoyxwz",  # CNFT Vault
    "noopb9bkMVfRPU8AsbpTUg8AQkHtKwMYZiFUjNRtMmV",   # Noop Program
    "11111111111111111111111111111111",                 # System Program
}

class IndexerErrorHandler:
    """Centralized error handling for the indexer."""
    
    def __init__(self):
        self.logger = logging.getLogger('indexer.error_handler')
        self.error_counts = {}
        self.last_error_time = {}
    
    def should_retry_error(self, error: Exception, signature: str = None) -> bool:
        """Determine if an error should trigger a retry."""
        error_type = type(error).__name__
        
        # Don't retry these error types
        non_retryable_errors = {
            'AttributeError',  # Usually code bugs
            'TypeError',       # Usually code bugs  
            'KeyError',        # Missing expected data
            'ValueError',      # Invalid data format
        }
        
        if error_type in non_retryable_errors:
            self.logger.warning(f"Non-retryable error {error_type} for {signature}: {error}")
            return False
            
        # Retry network and temporary errors
        retryable_errors = {
            'ConnectionError',
            'TimeoutError', 
            'HTTPError',
            'aiohttp.ClientError',
        }
        
        if error_type in retryable_errors:
            return True
            
        # Check error message for rate limiting
        error_msg = str(error).lower()
        if any(phrase in error_msg for phrase in ['rate limit', 'too many requests', '429']):
            return True
            
        return False
    
    def log_error(self, error: Exception, context: Dict[str, Any]):
        """Log error with context information."""
        error_type = type(error).__name__
        
        # Track error frequency
        error_key = f"{error_type}:{context.get('function', 'unknown')}"
        current_time = datetime.now()
        
        if error_key in self.error_counts:
            self.error_counts[error_key] += 1
        else:
            self.error_counts[error_key] = 1
            
        self.last_error_time[error_key] = current_time
        
        # Log with different levels based on frequency
        error_count = self.error_counts[error_key]
        
        log_data = {
            'error_type': error_type,
            'error_message': str(error),
            'error_count': error_count,
            'context': context,
            'timestamp': current_time.isoformat()
        }
        
        if error_count == 1:
            self.logger.error(f"First occurrence of error: {json.dumps(log_data, indent=2)}")
        elif error_count <= 5:
            self.logger.warning(f"Error #{error_count}: {error_type} - {error}")
        elif error_count % 10 == 0:
            self.logger.error(f"Frequent error (#{error_count}): {error_type} - {error}")
        else:
            self.logger.debug(f"Repeated error #{error_count}: {error_type}")

class TransactionValidator:
    """Validate transactions before processing."""
    
    @staticmethod
    def is_valid_transaction(tx_details: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validate if transaction is worth processing.
        
        Returns:
            tuple: (is_valid, reason)
        """
        if not tx_details:
            return False, "Empty transaction details"
            
        signature = tx_details.get('signature')
        if not signature:
            return False, "Missing transaction signature"
            
        event_type = tx_details.get('type', '').upper()
        if event_type in SKIP_EVENT_TYPES:
            return False, f"Skipping event type: {event_type}"
            
        # Check for NFT-related programs
        instructions = tx_details.get('instructions', [])
        if not instructions:
            return False, "No instructions in transaction"
            
        program_ids = {ix.get('programId') for ix in instructions if ix.get('programId')}
        
        # Must have at least one NFT-related program
        if not program_ids.intersection(NFT_PROGRAM_IDS):
            # Check token transfers for NFT-like characteristics
            token_transfers = tx_details.get('tokenTransfers', [])
            has_nft_transfer = False
            
            for transfer in token_transfers:
                if isinstance(transfer, dict):
                    token_amount = transfer.get('tokenAmount', {})
                    if isinstance(token_amount, dict):
                        decimals = token_amount.get('decimals', 0)
                        amount = token_amount.get('amount', '0')
                        # NFTs typically have 0 decimals and amount of 1
                        if decimals == 0 and amount == '1':
                            has_nft_transfer = True
                            break
                            
            if not has_nft_transfer:
                return False, "No NFT-related programs or transfers found"
                
        return True, "Valid NFT transaction"
    
    @staticmethod
    def sanitize_token_transfers(token_transfers: list) -> list:
        """Sanitize token transfers to handle malformed data."""
        sanitized = []
        
        for i, transfer in enumerate(token_transfers):
            if isinstance(transfer, dict):
                # Validate required fields
                if 'fromTokenAccount' in transfer and 'toTokenAccount' in transfer:
                    sanitized.append(transfer)
                else:
                    logging.warning(f"Token transfer {i} missing required fields")
            elif isinstance(transfer, (int, float)):
                logging.warning(f"Token transfer {i} is numeric value: {transfer}")
                # Could try to reconstruct as dict if more context available
            else:
                logging.warning(f"Token transfer {i} has unknown format: {type(transfer)}")
                
        return sanitized

class PerformanceMonitor:
    """Monitor indexer performance and health."""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.processed_transactions = 0
        self.failed_transactions = 0
        self.skipped_transactions = 0
        self.last_report_time = datetime.now()
        
    def record_transaction(self, status: str):
        """Record transaction processing result."""
        if status == 'processed':
            self.processed_transactions += 1
        elif status == 'failed':
            self.failed_transactions += 1
        elif status == 'skipped':
            self.skipped_transactions += 1
            
    def should_report(self, interval_minutes: int = 5) -> bool:
        """Check if it's time to report performance."""
        now = datetime.now()
        return (now - self.last_report_time).total_seconds() >= (interval_minutes * 60)
        
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate performance report."""
        now = datetime.now()
        uptime = now - self.start_time
        total_transactions = self.processed_transactions + self.failed_transactions + self.skipped_transactions
        
        report = {
            'uptime_seconds': uptime.total_seconds(),
            'total_transactions': total_transactions,
            'processed_transactions': self.processed_transactions,
            'failed_transactions': self.failed_transactions,
            'skipped_transactions': self.skipped_transactions,
            'success_rate': (self.processed_transactions / total_transactions * 100) if total_transactions > 0 else 0,
            'transactions_per_minute': (total_transactions / (uptime.total_seconds() / 60)) if uptime.total_seconds() > 0 else 0,
            'timestamp': now.isoformat()
        }
        
        self.last_report_time = now
        return report

