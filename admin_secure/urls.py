"""
admin_secure/urls.py
URL patterns for admin_secure app.
"""

from django.urls import path
from . import views

app_name = 'admin_secure'

urlpatterns = [
    path('decrypt/<int:secret_id>/', views.decrypt_secret_view, name='decrypt_secret'),
    path('rotate/<int:secret_id>/', views.rotate_secret_view, name='rotate_secret'),
    path('stats/', views.secret_access_stats, name='access_stats'),
]
