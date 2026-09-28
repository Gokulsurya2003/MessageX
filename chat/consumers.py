import asyncio
import json
from datetime import timedelta
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from django.utils import timezone
from django.db.models import F

from .models import ChatUser


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.room_group_name = "random_chat"
        self.username = await self.get_username()
        self.connection_registered = False

        if self.username:
            self.user_group_name = f"user_{self.username}"

            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )

            await self.add_connection()

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        self.monitor_task = asyncio.create_task(
            self.monitor_heartbeat()
        )

    async def disconnect(self, close_code):
        if hasattr(self, "monitor_task"):
            self.monitor_task.cancel()

        print("WEBSOCKET DISCONNECTED:", self.username)

        if self.username:

            matched_username = await self.get_matched_username()

            remaining_connections = await self.remove_connection()

            print(
                "REMAINING CONNECTIONS:",
                self.username,
                remaining_connections
            )

            if remaining_connections == 0 and matched_username:
                asyncio.create_task(
                    self.delayed_match_cleanup(
                        matched_username
                    )
                )

            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )

        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def delayed_match_cleanup(self, matched_username):

        await asyncio.sleep(8)

        connection_count = await self.get_connection_count()

        if connection_count > 0:
            print(
                "USER RECONNECTED - KEEP MATCH:",
                self.username
            )
            return

        await self.clear_match_for_both(
            matched_username
        )

        await self.channel_layer.group_send(
            f"user_{matched_username}",
            {
                "type": "match_ended"
            }
        )

        print(
            "MATCH ENDED - USER OFFLINE:",
            self.username,
            matched_username
        )

    async def receive(self, text_data):

        data = json.loads(text_data)

        if data.get("type") == "heartbeat":
            await self.update_heartbeat()
            return

        message = data.get("message", "")
        sender = data.get("sender")

        if not message:
            return

        print("MESSAGE RECEIVED:", message)

        matched_username = await self.get_active_match()

        if not matched_username:

            print(
                "NO ACTIVE MATCH - MESSAGE NOT SENT"
            )

            await self.send(
                text_data=json.dumps({
                    "type": "chat_inactive"
                })
            )

            return

        await self.channel_layer.group_send(
            self.user_group_name,
            {
                "type": "chat_message",
                "message": message,
                "sender": sender,
            }
        )

        await self.channel_layer.group_send(
            f"user_{matched_username}",
            {
                "type": "chat_message",
                "message": message,
                "sender": sender,
            }
        )

    async def chat_message(self, event):

        await self.send(
            text_data=json.dumps({
                "type": "chat_message",
                "message": event["message"],
                "sender": event["sender"]
            })
        )

    async def match_found(self, event):

        await self.send(
            text_data=json.dumps({
                "type": "match_found",
                "matched_username":
                    event["matched_username"]
            })
        )

    async def match_ended(self, event):

        await self.send(
            text_data=json.dumps({
                "type": "match_ended"
            })
        )

    @database_sync_to_async
    def get_username(self):

        username = self.scope["session"].get(
            "username"
        )

        if username:
            return username

        query_string = self.scope.get(
            "query_string",
            b""
        ).decode()

        params = parse_qs(query_string)

        username_list = params.get(
            "username"
        )

        if username_list:
            return username_list[0]

        return None

    @database_sync_to_async
    def add_connection(self):

        user = ChatUser.objects.filter(
            username=self.username
        ).first()

        if user:

            ChatUser.objects.filter(
                pk=user.pk
            ).update(
                connection_count=F(
                    "connection_count"
                ) + 1,
                is_online=True,
                last_seen=timezone.now()
            )

            self.connection_registered = True

            print(
                "CONNECTION ADDED:",
                self.username
            )

    @database_sync_to_async
    def remove_connection(self):

        if not self.connection_registered:
            return 0

        user = ChatUser.objects.filter(
            username=self.username
        ).first()

        if not user:
            return 0

        new_count = max(
            user.connection_count - 1,
            0
        )

        user.connection_count = new_count

        if new_count == 0:
            user.is_online = False

        user.last_seen = timezone.now()

        user.save(
            update_fields=[
                "connection_count",
                "is_online",
                "last_seen"
            ]
        )

        self.connection_registered = False

        print(
            "CONNECTION REMOVED:",
            self.username,
            new_count
        )

        return new_count

    @database_sync_to_async
    def get_connection_count(self):

        user = ChatUser.objects.filter(
            username=self.username
        ).first()

        if not user:
            return 0

        return user.connection_count

    @database_sync_to_async
    def check_heartbeat(self):

        user = ChatUser.objects.filter(
            username=self.username
        ).first()

        if not user or not user.last_seen:
            return True

        cutoff = timezone.now() - timedelta(
            seconds=8
        )

        return user.last_seen < cutoff

    async def monitor_heartbeat(self):

        try:

            while True:

                await asyncio.sleep(5)

                is_stale = await self.check_heartbeat()

                if is_stale:

                    await self.set_offline()

                    print(
                        "HEARTBEAT EXPIRED:",
                        self.username
                    )

                    return

        except asyncio.CancelledError:
            pass

    @database_sync_to_async
    def set_offline(self):

        user = ChatUser.objects.filter(
            username=self.username
        ).first()

        if user and user.connection_count == 0:

            user.is_online = False

            user.save(
                update_fields=[
                    "is_online"
                ]
            )

            print(
                "AUTO OFFLINE:",
                user.username
            )

    @database_sync_to_async
    def update_heartbeat(self):

        user = ChatUser.objects.filter(
            username=self.username
        ).first()

        if user:

            user.is_online = True
            user.last_seen = timezone.now()

            user.save(
                update_fields=[
                    "is_online",
                    "last_seen"
                ]
            )

    @database_sync_to_async
    def get_matched_username(self):

        user = ChatUser.objects.filter(
            username=self.username,
            is_matched=True
        ).first()

        if user:
            return user.matched_with

        return None

    @database_sync_to_async
    def get_active_match(self):

        user = ChatUser.objects.filter(
            username=self.username,
            is_matched=True
        ).first()

        if not user or not user.matched_with:
            return None

        partner = ChatUser.objects.filter(
            username=user.matched_with
        ).first()

        if not partner:
            return None

        if (
            partner.is_matched
            and partner.matched_with == self.username
            and partner.connection_count > 0
        ):
            return partner.username

        return None

    @database_sync_to_async
    def clear_match_for_both(
        self,
        partner_username
    ):

        current_user = ChatUser.objects.filter(
            username=self.username
        ).first()

        partner = ChatUser.objects.filter(
            username=partner_username
        ).first()

        if current_user:

            if current_user.matched_with == partner_username:

                current_user.is_matched = False
                current_user.matched_with = None

                current_user.save()

        if partner:

            if partner.matched_with == self.username:

                partner.is_matched = False
                partner.matched_with = None

                partner.save()