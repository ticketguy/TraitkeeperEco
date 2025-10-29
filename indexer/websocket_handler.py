# indexer/websocket_handler.py - Real-time updates via WebSocket
import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from .background_task_manager import task_manager

class TaskManagerConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time task manager updates"""
    
    async def connect(self):
        # Check if user is staff
        if self.scope["user"] == AnonymousUser or not self.scope["user"].is_staff:
            await self.close()
            return
        
        await self.channel_layer.group_add("task_manager", self.channel_name)
        await self.accept()
        
        # Send initial status
        status = task_manager.get_status()
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'data': status
        }))
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("task_manager", self.channel_name)
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'get_status':
                status = task_manager.get_status()
                await self.send(text_data=json.dumps({
                    'type': 'status_update',
                    'data': status
                }))
            elif message_type == 'get_history':
                history = list(task_manager.task_history)[-20:]
                await self.send(text_data=json.dumps({
                    'type': 'history_update',
                    'data': history
                }))
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
    
    # Handler for broadcasting status updates
    async def task_status_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'data': event['data']
        }))