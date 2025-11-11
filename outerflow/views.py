from django.shortcuts import render


def outerflow_home(request):
    """Outerflow landing page - Coming Soon"""
    return render(request, 'outerflow/coming_soon.html', {
        'app_name': 'Outerflow',
        'app_description': 'Community-as-a-Service network. Empower NFT communities with task distribution, reputation tracking, and collaborative earning systems.',
        'features': [
            'Task & Service Distribution',
            'XP and Reputation System',
            'Transparent Contribution Logs',
            'Collaborative Earning'
        ]
    })
