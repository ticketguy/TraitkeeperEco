from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('mark-read/', views.mark_notification_read, name='mark_notification_read'),
    path('save-push-subscription/', views.save_push_subscription, name='save_push_subscription'),
    path('save-preferences/', views.save_notification_preferences, name='save_notification_preferences'),
]