from django.urls import path

from chat.consumers.chat_p2p_consumer import P2PChatConsumer
from chat.consumers.connect_consumer import ConnectConsumer
from chat.consumers.disconnect_consumer import DisconnectConsumer
from chat.consumers.scan_consumer import ScanConnectConsumer

websocket_urlpatterns = [
    path("ws/connect/", ConnectConsumer.as_asgi(), name="connect_consumer"),
    path(
        "ws/connect/scan/<uuid:did>/",
        ScanConnectConsumer.as_asgi(),
        name="scan_to_connect",
    ),
    path("ws/disconnect/", DisconnectConsumer.as_asgi(), name="disconnect_consumer"),
    path("ws/chat/p2p/", P2PChatConsumer.as_asgi(), name="chat_p2p_consumer"),
]
