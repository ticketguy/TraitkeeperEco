from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Max, Count
from nft_data.models import NFTCollection
from .models import CollectionEvent, NFTBurn, CollectionRaritySnapshot
from wallet.models import WalletProfile
from profiles.models import UserAchievement
from profiles.utils import award_achievement

class CollectionMemoriesView(LoginRequiredMixin, View):
    def get(self, request, collection_address):
        collection = get_object_or_404(NFTCollection, address=collection_address)
        
        # Handle filtering
        event_type_filter = request.GET.get('event_type', '')
        search_query = request.GET.get('search', '')

        # Get all events for the collection
        events = CollectionEvent.objects.filter(collection=collection)
        
        # Apply filters
        if event_type_filter:
            events = events.filter(event_type=event_type_filter.upper())
        if search_query:
            events = events.filter(Q(mint_address__icontains=search_query))

        events = events.order_by('timestamp')

        # Find highlights
        highlights = {
            "first_mint": CollectionEvent.objects.filter(collection=collection, event_type="MINT").order_by('timestamp').first(),
            "highest_sale": CollectionEvent.objects.filter(collection=collection, event_type="SALE").order_by('-details__price').first(),
            "most_interacted_burn": CollectionEvent.objects.filter(collection=collection, event_type="BURN").annotate(
                total_likes=Count('user_interactions__likes')
            ).order_by('-total_likes').first(),
        }

        timeline = [
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "mint_address": event.mint_address,
                "details": event.details,
                "timestamp": event.timestamp.isoformat(),
                "significance": event.significance,
                "user_interactions": event.user_interactions,
                "can_add_interaction": request.user.is_authenticated,
                "is_highlight": (
                    (highlights["first_mint"] and event.event_id == highlights["first_mint"].event_id) or
                    (highlights["highest_sale"] and event.event_id == highlights["highest_sale"].event_id) or
                    (highlights["most_interacted_burn"] and event.event_id == highlights["most_interacted_burn"].event_id)
                )
            }
            for event in events
        ]

        # Get burned NFTs with details
        burned_nfts = NFTBurn.objects.filter(collection=collection).order_by('-timestamp')
        burned_nfts_data = []
        for burn in burned_nfts:
            # Check if the current user can add a reason
            can_add_reason = False
            if request.user.is_authenticated and burn.burner:
                try:
                    user_profile = WalletProfile.objects.get(user=request.user)
                    if user_profile.public_key == burn.burner:
                        can_add_reason = True
                except WalletProfile.DoesNotExist:
                    pass

            burned_nfts_data.append({
                "burn_id": burn.burn_id,
                "mint_address": burn.mint_address,
                "burner": burn.burner,
                "timestamp": burn.timestamp.isoformat(),
                "name": burn.name,
                "description": burn.description,
                "image_url": burn.image_url,
                "number": burn.number,
                "rarity": burn.rarity,
                "reason": burn.reason if burn.reason_is_approved else "Reason pending approval" if burn.reason else "No reason provided.",
                "reason_is_approved": burn.reason_is_approved,
                "user_interactions": burn.user_interactions,
                "can_add_reason": can_add_reason,
                "can_add_interaction": request.user.is_authenticated,
                "history": [
                    {
                        "event_type": event.event_type,
                        "details": event.details,
                        "timestamp": event.timestamp.isoformat(),
                        "significance": event.significance,
                        "user_interactions": event.user_interactions,
                    }
                    for event in CollectionEvent.objects.filter(collection=collection, mint_address=burn.mint_address).order_by('timestamp')
                ]
            })

        # Get rarity snapshots
        rarity_snapshots = CollectionRaritySnapshot.objects.filter(collection=collection).order_by('timestamp')
        rarity_history = [
            {
                "timestamp": snapshot.timestamp.isoformat(),
                "total_supply": snapshot.total_supply,
                "rarity_base": snapshot.rarity_base,
            }
            for snapshot in rarity_snapshots
        ]

        # Get user's points (for gamification)
        user_points = 0
        if request.user.is_authenticated:
            achievements = UserAchievement.objects.filter(user=request.user)
            user_points = sum(achievement.points for achievement in achievements)

        context = {
            "collection": collection,
            "timeline": timeline,
            "total_events": len(timeline),
            "burned_nfts": burned_nfts_data,
            "rarity_history": rarity_history,
            "event_type_filter": event_type_filter,
            "search_query": search_query,
            "user_points": user_points,
            "event_types": [choice[0] for choice in CollectionEvent.EVENT_TYPES],  # For filter dropdown
        }
        return render(request, 'nft_memories/collection_memories.html', context)

    def post(self, request, collection_address):
        collection = get_object_or_404(NFTCollection, address=collection_address)
        action = request.POST.get('action')

        if action == "add_burn_reason":
            burn_id = request.POST.get('burn_id')
            reason = request.POST.get('reason', '').strip()

            if not burn_id or not reason:
                messages.error(request, "Burn ID and reason are required.")
                return redirect('nft_memories:collection_memories', collection_address=collection_address)

            try:
                burn = NFTBurn.objects.get(burn_id=burn_id, collection=collection)
            except NFTBurn.DoesNotExist:
                messages.error(request, "Burn event not found.")
                return redirect('nft_memories:collection_memories', collection_address=collection_address)

            # Check if the current user is authorized to add a reason
            try:
                user_profile = WalletProfile.objects.get(user=request.user)
                if user_profile.public_key != burn.burner:
                    messages.error(request, "You are not authorized to add a reason for this burn.")
                    return redirect('nft_memories:collection_memories', collection_address=collection_address)
            except WalletProfile.DoesNotExist:
                messages.error(request, "You must have a linked wallet to add a burn reason.")
                return redirect('nft_memories:collection_memories', collection_address=collection_address)

            burn.reason = reason
            burn.reason_is_approved = False  # Require moderation
            burn.added_by_user = request.user
            burn.save()

            # Award achievement for adding a burn reason (NO POINTS for burns per user request)
            # Note: This is social/community contribution, not trading achievement
            messages.success(request, "Burn reason submitted for moderation!")
            return redirect('nft_memories:collection_memories', collection_address=collection_address)

        elif action in ["like", "comment", "tribute", "react"]:
            target_type = request.POST.get('target_type')  # "event" or "burn"
            target_id = request.POST.get('target_id')

            if target_type == "event":
                try:
                    target = CollectionEvent.objects.get(event_id=target_id, collection=collection)
                except CollectionEvent.DoesNotExist:
                    messages.error(request, "Event not found.")
                    return redirect('nft_memories:collection_memories', collection_address=collection_address)
            elif target_type == "burn":
                try:
                    target = NFTBurn.objects.get(burn_id=target_id, collection=collection)
                except NFTBurn.DoesNotExist:
                    messages.error(request, "Burned NFT not found.")
                    return redirect('nft_memories:collection_memories', collection_address=collection_address)
            else:
                messages.error(request, "Invalid target type.")
                return redirect('nft_memories:collection_memories', collection_address=collection_address)

            # Update user_interactions (NO POINTS for memories per user request)
            interactions = target.user_interactions

            if action == "like":
                interactions["likes"] = interactions.get("likes", 0) + 1

            elif action == "comment":
                comment_text = request.POST.get('comment', '').strip()
                if not comment_text:
                    messages.error(request, "Comment cannot be empty.")
                    return redirect('nft_memories:collection_memories', collection_address=collection_address)
                interactions["comments"].append({
                    "user": request.user.username,
                    "comment": comment_text,
                    "timestamp": timezone.now().isoformat()
                })

            elif action == "tribute":
                tribute_type = request.POST.get('tribute_type', '').strip()
                if not tribute_type:
                    messages.error(request, "Tribute type cannot be empty.")
                    return redirect('nft_memories:collection_memories', collection_address=collection_address)
                interactions["tributes"].append({
                    "user": request.user.username,
                    "tribute": tribute_type,
                    "timestamp": timezone.now().isoformat()
                })

            elif action == "react":
                reaction_type = request.POST.get('reaction_type', '').strip()
                if reaction_type not in ["fire", "heartbreak", "party"]:
                    messages.error(request, "Invalid reaction type.")
                    return redirect('nft_memories:collection_memories', collection_address=collection_address)
                reactions = interactions.get("reactions", {"fire": 0, "heartbreak": 0, "party": 0})
                reactions[reaction_type] = reactions.get(reaction_type, 0) + 1
                interactions["reactions"] = reactions

            target.user_interactions = interactions
            target.save()

            # Note: No points awarded for memories interactions per user request
            # This is purely social/memorial, not tied to airdrop-worthy achievements
            messages.success(request, f"{action.capitalize()} added successfully!")
            return redirect('nft_memories:collection_memories', collection_address=collection_address)

        messages.error(request, "Invalid action.")
        return redirect('nft_memories:collection_memories', collection_address=collection_address)

class EventDetailView(LoginRequiredMixin, View):
    def get(self, request, collection_address, event_id):
        collection = get_object_or_404(NFTCollection, address=collection_address)
        event = get_object_or_404(CollectionEvent, event_id=event_id, collection=collection)

        event_data = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "mint_address": event.mint_address,
            "details": event.details,
            "timestamp": event.timestamp.isoformat(),
            "significance": event.significance,
            "user_interactions": event.user_interactions,
            "can_add_interaction": request.user.is_authenticated,
        }

        # Get user's points
        user_points = 0
        if request.user.is_authenticated:
            achievements = UserAchievement.objects.filter(user=request.user)
            user_points = sum(achievement.points for achievement in achievements)

        context = {
            "collection": collection,
            "event": event_data,
            "user_points": user_points,
        }
        return render(request, 'nft_memories/event_detail.html', context)

    def post(self, request, collection_address, event_id):
        collection = get_object_or_404(NFTCollection, address=collection_address)
        event = get_object_or_404(CollectionEvent, event_id=event_id, collection=collection)
        action = request.POST.get('action')

        if action in ["like", "comment", "tribute", "react"]:
            interactions = event.user_interactions

            if action == "like":
                interactions["likes"] = interactions.get("likes", 0) + 1

            elif action == "comment":
                comment_text = request.POST.get('comment', '').strip()
                if not comment_text:
                    messages.error(request, "Comment cannot be empty.")
                    return redirect('nft_memories:event_detail', collection_address=collection_address, event_id=event_id)
                interactions["comments"].append({
                    "user": request.user.username,
                    "comment": comment_text,
                    "timestamp": timezone.now().isoformat()
                })

            elif action == "tribute":
                tribute_type = request.POST.get('tribute_type', '').strip()
                if not tribute_type:
                    messages.error(request, "Tribute type cannot be empty.")
                    return redirect('nft_memories:event_detail', collection_address=collection_address, event_id=event_id)
                interactions["tributes"].append({
                    "user": request.user.username,
                    "tribute": tribute_type,
                    "timestamp": timezone.now().isoformat()
                })

            elif action == "react":
                reaction_type = request.POST.get('reaction_type', '').strip()
                if reaction_type not in ["fire", "heartbreak", "party"]:
                    messages.error(request, "Invalid reaction type.")
                    return redirect('nft_memories:event_detail', collection_address=collection_address, event_id=event_id)
                reactions = interactions.get("reactions", {"fire": 0, "heartbreak": 0, "party": 0})
                reactions[reaction_type] = reactions.get(reaction_type, 0) + 1
                interactions["reactions"] = reactions

            event.user_interactions = interactions
            event.save()

            # Note: No points awarded for memories interactions per user request
            messages.success(request, f"{action.capitalize()} added successfully!")
            return redirect('nft_memories:event_detail', collection_address=collection_address, event_id=event_id)

        messages.error(request, "Invalid action.")
        return redirect('nft_memories:event_detail', collection_address=collection_address, event_id=event_id)

class ModerateBurnReasonsView(LoginRequiredMixin, View):
    def get(self, request):
        if not request.user.is_staff:
            messages.error(request, "You are not authorized to access this page.")
            return redirect('nft_memories:collection_memories', collection_address=collection.address)

        pending_reasons = NFTBurn.objects.filter(reason__isnull=False, reason_is_approved=False).order_by('-created_at')
        context = {
            "pending_reasons": [
                {
                    "burn_id": burn.burn_id,
                    "collection": burn.collection,
                    "mint_address": burn.mint_address,
                    "burner": burn.burner,
                    "reason": burn.reason,
                    "timestamp": burn.timestamp.isoformat(),
                }
                for burn in pending_reasons
            ]
        }
        return render(request, 'nft_memories/moderate_burn_reasons.html', context)

    def post(self, request):
        if not request.user.is_staff:
            messages.error(request, "You are not authorized to access this page.")
            return redirect('nft_memories:collection_memories', collection_address=collection.address)

        burn_id = request.POST.get('burn_id')
        action = request.POST.get('action')

        try:
            burn = NFTBurn.objects.get(burn_id=burn_id)
        except NFTBurn.DoesNotExist:
            messages.error(request, "Burn event not found.")
            return redirect('nft_memories:moderate_burn_reasons')

        if action == "approve":
            burn.reason_is_approved = True
            burn.save()
            messages.success(request, "Burn reason approved.")
        elif action == "reject":
            burn.reason = ""
            burn.reason_is_approved = False
            burn.save()
            messages.success(request, "Burn reason rejected.")
        else:
            messages.error(request, "Invalid action.")

        return redirect('nft_memories:moderate_burn_reasons')