# nft_data/views.py

from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
import logging

from .forms import CollectionSubmissionForm
from .models import NFTCollection, PendingCollection
from indexer.background_task_manager import background_task_manager, Task, TaskPriority

logger = logging.getLogger(__name__)


# REMOVED @csrf_exempt DECORATOR FOR SECURITY
def submit_collection(request):
    """
    Handles the user-facing collection submission form.
    Validation is delegated to the form, and notifications are handled by signals.
    """
    if request.method == 'POST':
        form = CollectionSubmissionForm(request.POST)
        # Basic validation: format, duplicates, required fields (no RPC calls)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.submitted_by = request.user.username if request.user.is_authenticated else "Anonymous"
            submission.status = 'validating'  # Start in validating status

            # Save immediately - user gets instant feedback
            submission.save()

            # Queue background task for on-chain validation
            from .tasks import validate_collection_onchain
            task = Task(
                id=f"validate_collection_{submission.mint_address}_{int(timezone.now().timestamp())}",
                name=f"Validate Collection {submission.name}",
                function=validate_collection_onchain,
                args=(submission.id,),
                priority=TaskPriority.HIGH
            )
            background_task_manager.add_task(task)

            logger.info(f"✅ Collection {submission.mint_address} submitted - queued for background validation")
            messages.success(
                request,
                "✅ Collection submitted successfully! We're verifying it on-chain. "
                "You'll be notified once validation is complete."
            )
            return redirect('submit_collection')
        else:
            # If the form is invalid, errors are automatically attached to the form
            # and will be displayed in the template. No need for manual messages.
            logger.warning(f"Collection submission failed validation: {form.errors.as_json()}")

    else: # GET request
        form = CollectionSubmissionForm()
        
    return render(request, 'nft_data/submit_collection.html', {'form': form})