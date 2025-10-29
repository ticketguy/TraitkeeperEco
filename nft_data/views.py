# nft_data/views.py

from django.shortcuts import render, redirect
from django.contrib import messages
import logging
# No longer need csrf_exempt
# from django.views.decorators.csrf import csrf_exempt

# Removed unused imports: AdminUser, AdminNotification, async_to_sync, etc.
# These responsibilities are moved to the form and signals.
from .forms import CollectionSubmissionForm
from .models import NFTCollection, PendingCollection # Kept for context if needed

logger = logging.getLogger(__name__)


# REMOVED @csrf_exempt DECORATOR FOR SECURITY
def submit_collection(request):
    """
    Handles the user-facing collection submission form.
    Validation is delegated to the form, and notifications are handled by signals.
    """
    if request.method == 'POST':
        form = CollectionSubmissionForm(request.POST)
        # All complex validation now happens inside form.is_valid()
        if form.is_valid():
            # The form has already validated the mint address, checked for duplicates,
            # and confirmed it's a real collection via an API call.
            submission = form.save(commit=False)
            submission.submitted_by = request.user.username if request.user.is_authenticated else "Anonymous"
            
            # The post_save signal will automatically fire here, sending the notification.
            submission.save() 
            
            messages.success(request, "Collection submitted successfully! It will be reviewed by an admin.")
            return redirect('submit_collection')
        else:
            # If the form is invalid, errors are automatically attached to the form
            # and will be displayed in the template. No need for manual messages.
            logger.warning(f"Collection submission failed validation: {form.errors.as_json()}")

    else: # GET request
        form = CollectionSubmissionForm()
        
    return render(request, 'nft_data/submit_collection.html', {'form': form})