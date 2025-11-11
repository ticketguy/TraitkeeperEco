from django.shortcuts import render


def popbox_home(request):
    """PopBox landing page - Coming Soon"""
    return render(request, 'popbox/coming_soon.html', {
        'app_name': 'PopBox',
        'app_description': 'Next-generation trading card marketplace for NFTs. Buy, sell, and trade NFT cards with seamless peer-to-peer transactions on Solana.',
        'features': [
            'Trading Card Marketplace',
            'Peer-to-Peer Trading',
            'Instant Settlements',
            'Rarity-Based Pricing'
        ]
    })
