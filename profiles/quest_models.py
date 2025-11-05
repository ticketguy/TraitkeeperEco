# profiles/quest_models.py
"""
Quest models that mirror the on-chain Solana quest program.
These are used by admins to create/manage quests before deploying them on-chain.
"""
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


class Quest(models.Model):
    """
    Represents a quest that users can complete to earn SOL rewards.
    Mirrors the QuestConfig struct in the Solana program.
    """

    ACTION_TYPES = [
        ('buy', 'Buy NFTs'),
        ('bid', 'Place Bids'),
        ('list', 'List NFTs'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),  # Not deployed yet
        ('pending', 'Pending Deployment'),  # Ready to deploy
        ('active', 'Active'),  # Deployed and active on-chain
        ('inactive', 'Inactive'),  # Deployed but disabled on-chain
        ('completed', 'Completed'),  # Quest ended
    ]

    # Quest identification
    quest_id = models.BigIntegerField(
        unique=True,
        help_text="Unique quest ID (u64) used on-chain"
    )

    # Quest details
    title = models.CharField(
        max_length=100,
        help_text="Display name for the quest"
    )
    description = models.TextField(
        help_text="Detailed description of what users need to do"
    )

    # Quest requirements
    action_type = models.CharField(
        max_length=10,
        choices=ACTION_TYPES,
        help_text="Type of action required"
    )
    target_count = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Number of actions required to complete (u32)"
    )

    # Rewards
    reward_lamports = models.BigIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Reward in lamports (1 SOL = 1,000,000,000 lamports)"
    )

    # Status and activation
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        help_text="Current status of the quest"
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Whether the quest is active on-chain"
    )

    # Display settings
    icon = models.CharField(
        max_length=50,
        blank=True,
        default='🎯',
        help_text="Emoji or icon for the quest"
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order (lower numbers shown first)"
    )

    # Timing
    start_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the quest becomes available"
    )
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the quest expires"
    )

    # On-chain tracking
    on_chain_address = models.CharField(
        max_length=44,
        blank=True,
        help_text="Solana address of the deployed quest PDA"
    )
    deployment_signature = models.CharField(
        max_length=88,
        blank=True,
        help_text="Transaction signature of quest creation"
    )
    deployed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the quest was deployed on-chain"
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time on-chain status was synced"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'admin_panel.AdminUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quests_created'
    )

    class Meta:
        ordering = ['display_order', '-created_at']
        indexes = [
            models.Index(fields=['quest_id']),
            models.Index(fields=['status', 'is_active']),
            models.Index(fields=['action_type']),
        ]

    def __str__(self):
        return f"Quest #{self.quest_id}: {self.title}"

    @property
    def reward_sol(self):
        """Convert lamports to SOL for display"""
        return self.reward_lamports / 1_000_000_000

    @property
    def is_available(self):
        """Check if quest is currently available"""
        now = timezone.now()
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        return self.is_active

    @property
    def progress_description(self):
        """Human-readable progress description"""
        action_verbs = {
            'buy': 'Buy',
            'bid': 'Place bids on',
            'list': 'List'
        }
        verb = action_verbs.get(self.action_type, 'Complete')
        return f"{verb} {self.target_count} NFT{'s' if self.target_count > 1 else ''}"


class QuestUserProgress(models.Model):
    """
    Tracks a user's progress and claims for quests.
    This mirrors on-chain data but is cached for faster lookups.
    """
    user = models.ForeignKey(
        'wallet.CustomUser',
        on_delete=models.CASCADE,
        related_name='quest_progress'
    )

    # On-chain progress tracking
    nfts_bought = models.PositiveIntegerField(default=0)
    bids_placed = models.PositiveIntegerField(default=0)
    nfts_listed = models.PositiveIntegerField(default=0)

    # On-chain account info
    on_chain_address = models.CharField(
        max_length=44,
        blank=True,
        help_text="User's quest account PDA on Solana"
    )

    # Metadata
    last_synced_at = models.DateTimeField(
        auto_now=True,
        help_text="Last time progress was synced from on-chain"
    )

    class Meta:
        verbose_name_plural = "Quest user progress"
        indexes = [
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"{self.user.username}'s Quest Progress"


class QuestClaim(models.Model):
    """
    Records when a user claims a quest reward.
    """
    user = models.ForeignKey(
        'wallet.CustomUser',
        on_delete=models.CASCADE,
        related_name='quest_claims'
    )
    quest = models.ForeignKey(
        Quest,
        on_delete=models.CASCADE,
        related_name='claims'
    )

    # Claim details
    claimed_at = models.DateTimeField(auto_now_add=True)
    reward_lamports = models.BigIntegerField(
        help_text="Amount claimed (snapshot at claim time)"
    )

    # On-chain verification
    transaction_signature = models.CharField(
        max_length=88,
        help_text="Solana transaction signature of the claim"
    )

    class Meta:
        unique_together = ('user', 'quest')
        ordering = ['-claimed_at']
        indexes = [
            models.Index(fields=['user', '-claimed_at']),
            models.Index(fields=['quest', '-claimed_at']),
        ]

    def __str__(self):
        return f"{self.user.username} claimed {self.quest.title}"

    @property
    def reward_sol(self):
        """Convert lamports to SOL for display"""
        return self.reward_lamports / 1_000_000_000
