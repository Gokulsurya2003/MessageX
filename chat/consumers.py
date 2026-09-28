import asyncio
import json
from datetime import timedelta
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from django.utils import timezone

from .models import ChatUser


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):

        self.room_group_name = "random_chat"

        self.username = await self.get_username()

        if self.username:

            self.user_group_name = f"user_{self.username}"

            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )

            await self.set_online(True)

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

        print(
            "WEBSOCKET DISCONNECTED:",
            self.username
        )

        if self.username:

            matched_username = await self.get_matched_username()

            await self.set_online(False)

            print(
                "USER SET OFFLINE:",
                self.username
            )

            if matched_username:

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

    async def delayed_match_cleanup(
        self,
        matched_username
    ):

        await asyncio.sleep(8)

        still_online = await self.check_user_online()

        if still_online:

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

        print(
            "MESSAGE RECEIVED:",
            message
        )

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
                "matched_username": event[
                    "matched_username"
                ]
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

        username = self.scope["session"].get("username")

        if username:
            return username

        query_string = self.scope.get(
            "query_string",
            b""
        ).decode()

        params = parse_qs(query_string)

        username_list = params.get("username")

        if username_list:
            return username_list[0]

        return None

    @database_sync_to_async
    def set_online(self, status):

        user = ChatUser.objects.filter(
            username=self.username
        ).first()

        if user:

            user.is_online = status
            user.last_seen = timezone.now()

            user.save(
                update_fields=[
                    "is_online",
                    "last_seen"
                ]
            )

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
    def check_heartbeat(self):

        user = ChatUser.objects.filter(
            username=self.username
        ).first()

        if not user or not user.last_seen:
            return True

        cutoff = (
            timezone.now()
            - timedelta(seconds=8)
        )

        return user.last_seen < cutoff

    @database_sync_to_async
    def set_offline(self):

        user = ChatUser.objects.filter(
            username=self.username
        ).first()

        if user:

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
    def check_user_online(self):

        user = ChatUser.objects.filter(
            username=self.username
        ).first()

        if not user:
            return False

        return user.is_online

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
            and partner.is_online
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

            if (
                current_user.matched_with
                == partner_username
            ):

                current_user.is_matched = False
                current_user.matched_with = None

                current_user.save()

        if partner:

            if (
                partner.matched_with
                == self.username
            ):

                partner.is_matched = False
                partner.matched_with = None

                partner.save()