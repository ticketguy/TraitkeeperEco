import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import Notification, NotificationPreference

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.close()
        else:
            self.user = self.scope["user"]
            self.group_name = f"user_{self.user.id}_notifications"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notify(self, event):
        message = event["message"]
        event_type = event["event_type"]
        data = event["data"]

        # Check user preferences
        if await self.should_notify(event_type, data):
            # Save notification to database
            await self.save_notification(event_type, message, data)

            # Send notification to WebSocket client
            await self.send(text_data=json.dumps({
                "type": "notification",
                "event_type": event_type,
                "message": message,
                "data": data,
            }))

    @database_sync_to_async
    def should_notify(self, event_type, data):
        """Check if the user wants to be notified for this event type"""
        try:
            pref = NotificationPreference.objects.get(user=self.user, notification_type=event_type)
            if not pref.enabled:
                return False

            # For transactions, check minimum value if set
            if event_type == "transaction" and pref.transaction_min_value is not None:
                price = data.get("price", 0)
                return float(price) >= float(pref.transaction_min_value)
            return True
        except NotificationPreference.DoesNotExist:
            # Default to notifying if preference doesn’t exist
            return True

    @database_sync_to_async
    def save_notification(self, event_type, message, data):
        """Save the notification to the database"""
        Notification.objects.create(
            user=self.user,
            event_type=event_type,
            message=message,
            data=data,
        )