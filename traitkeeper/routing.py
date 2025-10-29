# traitkeeper/routing.py (project-level, alongside settings.py)
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import re_path, path
from notifications.consumers import NotificationConsumer  # Import directly from notifications app
from indexer import websocket_handler

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'traitkeeper.settings')

# Define WebSocket URL patterns directly in the project-level routing
websocket_urlpatterns = [
    re_path(r"ws/notifications/$", NotificationConsumer.as_asgi()),
    path('ws/task-manager/', websocket_handler.TaskManagerConsumer.as_asgi()),

]

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns
        )
    ),
})