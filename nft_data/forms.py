# nft_data/forms.py
from django import forms
from .models import PendingCollection, NFTCollection # Import NFTCollection for duplicate checks
# Import the main service that holds the validator
from .retrieval_services.nft_retrieval import NFTRetrievalService
import json
import re
from asgiref.sync import async_to_sync
import base58
import logging # Import logging

logger = logging.getLogger(__name__) # Add logger

class CollectionSubmissionForm(forms.ModelForm):
    social_media_links = forms.CharField(
        required=False,
        label="Social Media Links (JSON Format)",
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'e.g., {"twitter": "https://twitter.com/...", "discord": "https://discord.gg/..."}'
        }),
        help_text="Provide social media links in a valid JSON format."
    )

    class Meta:
        model = PendingCollection
        fields = ['mint_address', 'name', 'creator', 'description', 'image_url', 'social_media_links']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }


    def clean_mint_address(self):
        """
        Performs comprehensive validation on the collection's mint address.
        """
        mint_address = self.cleaned_data.get('mint_address', '').strip()
        if not mint_address:
            raise forms.ValidationError("This field is required.")

        # ✅ Step 1: Validate the Solana address format (Base58)
        try:
            decoded = base58.b58decode(mint_address)
            if len(decoded) != 32:
                raise forms.ValidationError("Invalid address: A Solana address must be a 32-byte public key.")
        except Exception:
            raise forms.ValidationError("Invalid address format: Please provide a valid Base58 encoded string.")

        # 🔍 Step 2: Check for duplicates in our database
        if NFTCollection.objects.filter(address=mint_address).exists():
            raise forms.ValidationError("This collection has already been approved and added.")
        # Check against current instance (useful for edits, though this form might be for creation only)
        current_pk = self.instance.pk if self.instance else None
        if PendingCollection.objects.filter(mint_address=mint_address, status='pending').exclude(pk=current_pk).exists():
            raise forms.ValidationError("This collection has already been submitted and is pending review.")

        # 🔗 Step 3: Perform a live check using the CollectionValidator service
        try:
            # Instantiate the main retrieval service which holds the validator
            logger.debug(f"Instantiating NFTRetrievalService for validation of {mint_address}")
            retrieval_service = NFTRetrievalService()

            # Call the validator's method asynchronously via async_to_sync
            logger.debug(f"Calling validator.validate_collection for {mint_address}")
            is_valid_on_chain = async_to_sync(retrieval_service.validator.validate_collection)(mint_address)
            logger.debug(f"Validation result for {mint_address}: {is_valid_on_chain}")

            if not is_valid_on_chain:
                raise forms.ValidationError(
                    "Validation Failed: We couldn't find a valid NFT collection on-chain at this address. "
                    "Please double-check the address. It should be the collection/group address, "
                    "not an individual NFT's mint address."
                )
            logger.info(f"✅ Successfully validated collection on-chain: {mint_address}")

        except forms.ValidationError:
             raise # Re-raise validation errors immediately
        except Exception as e:
            # Log the unexpected error
            logger.error(f"❌ Unexpected error during live validation for {mint_address}: {e}", exc_info=True)
            # Raise a user-friendly validation error
            raise forms.ValidationError(
                f"A service error occurred while validating the collection: {e}. Please try again later or contact support."
            )

        return mint_address


    def clean_social_media_links(self):
        social_media_data = self.cleaned_data.get('social_media_links', '')
        if not social_media_data:
            return {} # Return empty dict if field is empty

        try:
            social_media_links = json.loads(social_media_data)
            if not isinstance(social_media_links, dict):
                raise forms.ValidationError("Social media links must be a valid JSON object (key-value pairs).")

            # Basic URL validation (can be enhanced further)
            url_pattern = re.compile(r'^https://[^\s/$.?#].[^\s]*$')
            for platform, url in social_media_links.items():
                if not isinstance(url, str) or not url_pattern.match(url):
                    raise forms.ValidationError(f"Invalid URL format for {platform}: '{url}'. Must start with 'https://' and be a valid URL.")

            return social_media_links
        except json.JSONDecodeError:
            raise forms.ValidationError("Invalid JSON format. Please check your syntax (e.g., use double quotes for keys and string values).")
        except Exception as e: # Catch other potential errors during validation
             raise forms.ValidationError(f"Error validating social media links: {e}")

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Ensure social_media_links is saved correctly as JSON (or None if empty)
        cleaned_links = self.cleaned_data.get('social_media_links')
        instance.social_media_links = cleaned_links if cleaned_links else None
        if commit:
            instance.save()
        return instance