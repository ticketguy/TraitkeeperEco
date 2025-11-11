from django.shortcuts import render


def traitloom_home(request):
    """TraitLoom landing page - Coming Soon"""
    return render(request, 'traitloom/coming_soon.html', {
        'app_name': 'TraitLoom',
        'app_description': 'Dedicated trait marketplace for NFTs. Buy, sell, and exchange individual traits to customize and evolve your digital collectibles.',
        'features': [
            'Trait Trading Marketplace',
            'Trait Extraction & Merging',
            'Dynamic Trait Pricing',
            'NFT Evolution System'
        ]
    })
