import logging
import asyncio
# safe import: prefer asgiref.sync.sync_to_async, fallback to asyncio.to_thread
try:
    from asgiref.sync import sync_to_async  # type: ignore
except Exception:
    def sync_to_async(func):
        async def _wrapper(*args, **kwargs):
            return await asyncio.to_thread(func, *args, **kwargs)
        return _wrapper

from django.db import transaction
from django.utils import timezone
from notifications.services import NotificationService

from django.contrib.contenttypes.models import ContentType

from .models import NFTCollection, PendingCollection
from .retrieval_services.nft_retrieval import NFTRetrievalService
from admin_panel.models import AdminLogEntry, AdminUser
from notifications.models import AdminNotification
from indexer.services import IndexerService
 
logger = logging.getLogger(__name__)


class NFTDataService:
    """
    Manages the core lifecycle of NFT collections in the database. 🚀

    This service acts as a high-level orchestrator. It handles the administrative
    workflow for collections, such as validating new submissions, approving or
    rejecting them, and managing their public listing status.

    It delegates the heavy lifting of actual blockchain data fetching to the
    `NFTRetrievalService` and passes off indexing tasks to the `IndexerService`.
    """

    def __init__(self):
        """Initializes the service and its required sub-services."""
        # This service now only depends on the retrieval and indexer services.
        self.nft_retrieval_service = NFTRetrievalService()
        self.indexer_service = IndexerService()
        logger.info("NFTDataService initialized.")

    async def fetch_collection_for_validation(self, collection_address: str) -> bool:
        """
        Validates a collection address by checking for its existence on the blockchain.
        This is a wrapper around the more complex validation logic in the retrieval service.

        Args:
            collection_address (str): The public key of the collection to validate.

        Returns:
            bool: True if the collection is valid, False otherwise.
        """
        try:
            logger.info(f"Validating collection {collection_address}...")
            # Delegate the blockchain call to the specialized retrieval service.
            is_valid = await self.nft_retrieval_service.validate_collection(collection_address)
            if is_valid:
                logger.info(f"Successfully validated collection {collection_address}.")
                return True
            else:
                logger.warning(f"Failed to validate collection {collection_address}: Not a valid collection.")
                return False
        except Exception as e:
            logger.error(f"Error validating collection {collection_address}: {e}", exc_info=True)
            return False

    async def approve_pending_collection(self, pending_collection_id: int, approved_by_user) -> dict:
        """
        Approves a pending collection, fetches its data, saves it, and kicks off indexing.
        This is a critical administrative workflow.
        """
        try:
            # Use a helper function to perform synchronous database operations atomically.
            @sync_to_async
            def _approve_in_transaction():
                with transaction.atomic():
                    pending_collection = PendingCollection.objects.select_for_update().get(id=pending_collection_id)

                    if pending_collection.status != 'pending':
                        raise ValueError(f"Collection '{pending_collection.name}' is not in 'pending' state.")
                    
                    if NFTCollection.objects.filter(address=pending_collection.mint_address).exists():
                        raise ValueError(f"An approved collection with this address already exists.")

                    return pending_collection

            # Await the atomic database operation.
            pending_collection = await _approve_in_transaction()
            logger.info(f"Pending collection {pending_collection.mint_address} retrieved from DB.")

            # Call the retrieval service
            logger.info(f"Calling fetch_collections_by_collection for {pending_collection.mint_address}...")
            fetched_collections = await self.nft_retrieval_service.fetch_collections_by_collection(pending_collection.mint_address)
            
            if not fetched_collections:
                logger.error(f"fetch_collections_by_collection returned empty list for {pending_collection.mint_address}. Approval process failed.")
                return {"success": False, "error": "Failed to fetch and store collection data."}
            
            logger.info(f"fetch_collections_by_collection SUCCESSFUL for {pending_collection.mint_address}.")

            # Get the newly created collection and mark it as publicly visible.
            logger.info(f"Setting collection {pending_collection.mint_address} as listed...")
            new_collection = await sync_to_async(NFTCollection.objects.get)(address=pending_collection.mint_address)
            new_collection.is_listed = True
            await sync_to_async(new_collection.save)(update_fields=['is_listed'])
            
            # The pending entry is no longer needed, so delete it.
            logger.info(f"Deleting pending entry for {pending_collection.mint_address}...")
            await sync_to_async(pending_collection.delete)()

            # --- START OF FIX ---
            # We must wrap this synchronous DB call in sync_to_async
            @sync_to_async
            def get_content_type_id_async():
                return ContentType.objects.get_for_model(PendingCollection).pk

            # Call the async helper to get the ID
            pending_collection_content_type_id = await get_content_type_id_async()
            # --- END OF FIX ---

            # Log this administrative action to our custom admin log model.
            logger.info(f"Logging admin action for approval...")
            await sync_to_async(AdminLogEntry.objects.create)(
                user_id=approved_by_user.id,
                content_type_id=pending_collection_content_type_id, # Use the awaited variable
                object_id=pending_collection.id, 
                object_repr=str(pending_collection),
                action_flag=2, # "Change" (or "Addition" if you prefer)
                change_message="Approved collection"
            )
            
            # Send an in-app notification to all admins.
            logger.info(f"Sending approval notification...")
            NotificationService.create_admin_notification(
                subject=f"Collection Approved: {pending_collection.name}",
                message=f"The pending collection was approved by {approved_by_user.username}.",
                notification_type='collection_action', severity='info'
            )
            
            # Kick off the initial indexing and analytics for the new collection.
            logger.info(f"Initiating indexing for {new_collection.address}...")
            await self.indexer_service.update_collection_after_retrieval(new_collection.address)
            
            logger.info(f"Approval process completed successfully for {new_collection.address}.")
            return {"success": True}

        except (PendingCollection.DoesNotExist, ValueError) as e:
            # Handle expected errors like the collection not being found or already approved.
            return {"success": False, "error": str(e)}
        except Exception as e:
            # Handle unexpected errors during the process.
            logger.error(f"Error approving pending collection {pending_collection_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def reject_pending_collection(self, pending_collection_id: int, rejected_by_user) -> dict:
        """Marks a pending collection as rejected."""
        try:
            # Fetch the collection from the database.
            collection = await sync_to_async(PendingCollection.objects.get)(id=pending_collection_id)
            
            # Update its status and auditing fields.
            collection.status = 'rejected'
            collection.reviewed_by = rejected_by_user.username
            collection.reviewed_at = timezone.now()
            await sync_to_async(collection.save)()

            # Log the action and send a notification.
            await sync_to_async(AdminLogEntry.objects.create)(
                user_id=rejected_by_user.id,
                content_type_id=ContentType.objects.get_for_model(PendingCollection).pk,
                object_id=collection.id, object_repr=str(collection),
                action_flag=2, change_message="Rejected collection"
            )
            
            NotificationService.create_admin_notification(
                subject=f"Collection Rejected: {collection.name}",
                message=f"The pending collection was rejected by {rejected_by_user.username}.",
                notification_type='collection_action', severity='warning'
            )
            return {"success": True}
        except Exception as e:
            logger.error(f"Error rejecting collection {pending_collection_id}: {e}")
            return {"success": False, "error": str(e)}
    
    async def list_collection(self, collection_address: str) -> dict:
        """Marks an existing collection as publicly listed by setting `is_listed` to True."""
        try:
            collection = await sync_to_async(NFTCollection.objects.get)(address=collection_address)
            if collection.is_listed:
                return {"success": False, "error": "Collection is already listed."}
            
            collection.is_listed = True
            await sync_to_async(collection.save)(update_fields=['is_listed'])
            logger.info(f"Successfully listed collection {collection_address}.")
            return {"success": True}
        except NFTCollection.DoesNotExist:
            logger.error(f"Collection {collection_address} not found for listing.")
            return {"success": False, "error": "Collection not found."}

    async def delist_collection(self, collection_address: str) -> dict:
        try:
            # Validate input early
            if not collection_address:
                logger.error("No collection_address provided for delisting.")
                return {"success": False, "error": "Invalid collection address"}

            # Wrap sync ORM access in sync_to_async so we await coroutines only
            @sync_to_async
            def _get_collection_by_address(addr: str):
                return NFTCollection.objects.get(address=addr)

            @sync_to_async
            def _save_collection_unlisted(obj):
                obj.is_listed = False
                obj.save(update_fields=['is_listed'])
                return True

            # Load collection (await the coroutine returned by _get_collection_by_address)
            try:
                collection = await _get_collection_by_address(collection_address)
            except NFTCollection.DoesNotExist:
                logger.error(f"Collection {collection_address} not found for delisting.")
                return {"success": False, "error": "Collection not found."}
            except Exception as e:
                logger.exception(f"Unexpected error while loading {collection_address}: {e}")
                return {"success": False, "error": str(e)}

            # Do not await plain booleans or model instances
            if not getattr(collection, "is_listed", False):
                return {"success": False, "error": "Collection is already delisted."}

            try:
                saved = await _save_collection_unlisted(collection)  # saved is a boolean
                if saved:
                    logger.info(f"Successfully delisted collection {collection_address}.")
                    return {"success": True}
                return {"success": False, "error": "Failed to delist collection."}
            except Exception as e:
                logger.exception(f"Unexpected error while delisting {collection_address}: {e}")
                return {"success": False, "error": str(e)}

        except Exception as e:
            logger.exception(f"Delist collection top-level error: {e}")
            return {"success": False, "error": str(e)}

    async def populate_collection(self, collection_address: str = None):
        """
        Fetches and stores the full data for one or all pending collections.
        """
        logger.info("=== Starting Collection Population ===")
        collections_to_process = []
        if collection_address:
            collections_to_process.append(collection_address)
        else:
            # If no specific address is given, get all collections currently pending.
            pending = await sync_to_async(list)(
                PendingCollection.objects.filter(status='pending').values_list('mint_address', flat=True)
            )
            collections_to_process.extend(pending)

        if not collections_to_process:
            logger.info("No pending collections to populate.")
            return {"success": True, "message": "No pending collections found."}

        logger.info(f"Found {len(collections_to_process)} collection(s) to populate.")
        successful, failed, errors = 0, 0, {}

        for address in collections_to_process:
            logger.info(f"Processing collection: {address}")
            try:
                # Delegate the complex fetching and storing logic to the retrieval service.
                result = await self.nft_retrieval_service.fetch_and_store_collection(address)
                if result.get("success"):
                    logger.info(f"Successfully stored collection {address}")
                    successful += 1
                    # After storing, tell the indexer to start processing it.
                    await self.indexer_service.update_collection_after_retrieval(address)
                else:
                    failed += 1
                    errors[address] = result.get("error", "Unknown retrieval error.")
            except Exception as e:
                logger.error(f"An exception occurred while populating {address}: {e}", exc_info=True)
                failed += 1
                errors[address] = str(e)
        
        logger.info("=== Collection Population Complete ===")
        logger.info(f"Successful: {successful}, Failed: {failed}")
        return {"success": failed == 0, "successful": successful, "failed": failed, "errors": errors}

    async def _send_approval_notification(self, start_time: timezone.datetime, pending_id: int, approved_by: str, result: dict):
        """Helper method to construct and send admin notifications for the approval process."""
        if result.get("success"):
            severity, status = "info", "Success"
            message = "<strong>Pending Collection Approved</strong>"
            details = {"collection_address": result.get("collection_address")}
        else:
            severity, status = "error", "Failed"
            message = "<strong>Pending Collection Approval Failed</strong>"
            details = {"error": result.get("error")}

        details.update({
            "start_time": start_time.strftime('%Y-%m-%d %H:%M:%S'),
            "pending_collection_id": pending_id,
            "approved_by": approved_by,
            "status": status,
        })
        
        message_body = "".join([f"<br><strong>{key.replace('_', ' ').title()}:</strong> {value}" for key, value in details.items()])
        full_message = f"{message}{message_body}"

        # Get all admin users and send them an in-app notification.
        admin_users = await sync_to_async(list)(AdminUser.objects.filter(is_active=True, is_staff=True))
        for admin_user in admin_users:
            await sync_to_async(AdminNotification.objects.create)(
                type='pending_collection_approved',
                message=full_message,
                details=details,
                severity=severity,
                admin_user=admin_user,
            )