# Generated manually for Perception Index architectural refactoring
# Renames sentiment_score to perception_index across all vitality models
# Weight changes: Perception Index: 5% -> 20%, Market Momentum: 25% -> 10%

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0007_privatebid_amount_transactionmonitoring'),
    ]

    operations = [
        # Rename sentiment_score to perception_index in NFTVitality
        migrations.RenameField(
            model_name='nftvitality',
            old_name='sentiment_score',
            new_name='perception_index',
        ),

        # Rename sentiment_score to perception_index in NFTVitalityHistory
        migrations.RenameField(
            model_name='nftvitalityhistory',
            old_name='sentiment_score',
            new_name='perception_index',
        ),

        # Rename sentiment_score to perception_index in CollectionVitality
        migrations.RenameField(
            model_name='collectionvitality',
            old_name='sentiment_score',
            new_name='perception_index',
        ),

        # Rename sentiment_score to perception_index in CollectionVitalityHistory
        migrations.RenameField(
            model_name='collectionvitalityhistory',
            old_name='sentiment_score',
            new_name='perception_index',
        ),
    ]
