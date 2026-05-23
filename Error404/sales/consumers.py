import json
from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync

class CafeSyncConsumer(WebsocketConsumer):
    def connect(self):
        self.room_group_name = 'cafe_sync_group'
        # Join group
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        # Leave group
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from group broadcast
    def product_created_event(self, event):
        product = event['product']
        # Send message to WebSocket client
        self.send(text_data=json.dumps({
            'type': 'product.created',
            'product': product
        }))

    # Receive message from group broadcast
    def product_updated_event(self, event):
        product = event['product']
        # Send message to WebSocket client
        self.send(text_data=json.dumps({
            'type': 'product.updated',
            'product': product
        }))

    # Receive message from group broadcast
    def product_deleted_event(self, event):
        product_id = event['product_id']
        # Send message to WebSocket client
        self.send(text_data=json.dumps({
            'type': 'product.deleted',
            'product_id': product_id
        }))