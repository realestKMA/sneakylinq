import json
from json.decoder import JSONDecodeError

from django.utils import timezone

from chat.events import DEVICE_EVENT_TYPES, SCAN_EVENT_TYPES
from chat.lua_scripts import LuaScripts
from src.helpers import format_alias, is_valid_alias
from src.utils import (
    BaseAsyncJsonWebsocketConsumer,
    convert_array_to_dict,
    is_valid_uuid,
    redis_client,
)


class ConnectConsumer(BaseAsyncJsonWebsocketConsumer):
    """
    Connect Consumer will:

    1. Accept connections, checks if to keep or discard connection.
    2. Receive data to set device alias.
    3. Then Disconnect, when successfully completed.
    """

    async def connect(self):
        """
        Accept all connections at first.

        But only keep connection if the value at index 0 in the request subprotocol
        is a valid uuid4. If not, notify device and close connection.

        Because we need the uuid4 to keep track of connected devices.
        """

        try:
            self.did = self.scope["subprotocols"][0]
            await self.accept(subprotocol=self.did)
        except IndexError:
            await self.accept()
            await self.send_json(
                {
                    "event": DEVICE_EVENT_TYPES.DEVICE_CONNECT.value,
                    "status": False,
                    "message": "A valid uuid4 should be at index 0 in subprotocols",
                }
            )
            await self.close()
        else:
            if is_valid_uuid(self.did):
                # set instance variables device & device_groups values
                self.device = f"device:{self.did}"
                self.device_groups = f"{self.device}:groups"

                # execute this lua script
                try:
                    LuaScripts.set_alias_device(keys=[self.device], client=redis_client)
                except Exception:
                    pass

                # connection time-to-live date object
                ttl = timezone.now() + timezone.timedelta(hours=2)

                # store data as hash type in redis store, also set an expire
                # option to the device data in redis store using
                # the ttl as the value.
                redis_client.hset(
                    name=self.device,
                    mapping={
                        "did": f"{self.did}",
                        "channel": f"{self.channel_name}",
                        "ttl": ttl.timestamp(),
                    },
                )
                redis_client.expireat(self.device, ttl)

                # send device data back to client
                await self.send_json(
                    {
                        "event": DEVICE_EVENT_TYPES.DEVICE_CONNECT.value,
                        "status": True,
                        "message": "Current device data",
                        "data": convert_array_to_dict(
                            LuaScripts.get_device_data(
                                keys=[self.device],
                                client=redis_client,
                            )
                        ),
                    }
                )

            else:  # uuid is not valid
                await self.send_json(
                    {
                        "event": DEVICE_EVENT_TYPES.DEVICE_CONNECT.value,
                        "status": False,
                        "message": "A valid uuid4 should be at index 0 in subprotocols",
                    }
                )
                await self.close()

    async def receive(self, text_data=None):
        """Receive device alias and store in redis"""

        try:  # get device alias
            alias: str = json.loads(text_data)["alias"]
        except (TypeError, JSONDecodeError):
            await self.send_json(
                {
                    "event": DEVICE_EVENT_TYPES.DEVICE_SETUP.value,
                    "status": False,
                    "message": "Message(s) must be in json format",
                }
            )
        except KeyError as e:
            await self.send_json(
                {
                    "event": DEVICE_EVENT_TYPES.DEVICE_SETUP.value,
                    "status": False,
                    "message": f"Missing key {str(e)}",
                }
            )
        else:
            alias_msg, alias_name, alias_status = is_valid_alias(alias=alias)

            if alias_status:
                alias_msg, alias_name, alias_status = format_alias(
                    device=self.device, alias=alias_name
                )

                if alias_status:
                    # add the device alias to device:alias & alias:device hash
                    # in redis store
                    redis_client.hset(self.device_alias, key=self.device, value=alias_name)
                    redis_client.hset(self.alias_device, key=alias_name, value=self.device)

                    # connection time-to-live date object
                    ttl = timezone.now() + timezone.timedelta(hours=2)

                    # in redis store, update device data ttl value. And also set an expire
                    # option to the device data in redis store using the ttl as the value.
                    redis_client.hset(self.device, key="ttl", value=ttl.timestamp())
                    redis_client.expireat(self.device, ttl)

                    # SUCCESS: notify client.
                    await self.send_json(
                        {
                            "event": DEVICE_EVENT_TYPES.DEVICE_SETUP.value,
                            "status": True,
                            "message": alias_msg,
                            "data": convert_array_to_dict(
                                LuaScripts.get_device_data(keys=[self.device], client=redis_client)
                            ),
                        }
                    )

                    return

            # FAILURE: notify client
            await self.send_json(
                {
                    "event": DEVICE_EVENT_TYPES.DEVICE_SETUP.value,
                    "status": alias_status,
                    "message": alias_msg,
                    "data": {"alias": alias_name},
                }
            )

    async def chat_message(self, event):
        await self.send_json(event["data"])

    async def disconnect(self, code):
        redis_client.hdel(f"{self.device}", "channel")
        redis_client.hdel(
            self.alias_device,
            f"{redis_client.hget(f'{self.device_alias}', f'{self.device}')}",
        )


class ScanConnectConsumer(BaseAsyncJsonWebsocketConsumer):
    """
    Implements a scan to connect feature via QR Code scanning
    and carries out device setup.
    """

    async def connect(self):
        self.did = self.scope["url_route"]["kwargs"]["did"]
        self.device = f"device:{self.did}"
        self.device_groups = f"{self.device}:groups"

        await self.accept()

        if (
            redis_client.hget(self.device, key="channel")
            and redis_client.hget(self.device_alias, key=self.device) == None
        ):
            # SUCCESS: notify the client of the scanned device details
            await self.send_json(
                {
                    "event": SCAN_EVENT_TYPES.SCAN_CONNECT.value,
                    "status": True,
                    "message": "Scanned succeccfully",
                    "data": convert_array_to_dict(
                        LuaScripts.get_device_data(
                            keys=[self.device],
                            client=redis_client,
                        )
                    ),
                }
            )

            # SUCCESS: notify device with the qr code.
            await self.channel_layer.send(
                redis_client.hget(self.device, key="channel"),
                {
                    "type": "chat.message",
                    "data": {
                        "event": SCAN_EVENT_TYPES.SCAN_CONNECT.value,
                        "status": True,
                        "message": "Scanned successfully",
                    },
                },
            )

        else:
            # if device with channel already has an alias or channel not present
            await self.send_json(
                {
                    "event": SCAN_EVENT_TYPES.SCAN_CONNECT.value,
                    "status": False,
                    "message": "Invalid channel or device already setup",
                }
            )
            await self.close()

    async def receive(self, text_data=None, byte_data=None):
        """Receive device alias and store in redis"""

        try:
            alias: str = json.loads(text_data)["alias"]
        except KeyError as e:
            await self.send_json(
                {
                    "event": SCAN_EVENT_TYPES.SCAN_SETUP.value,
                    "status": False,
                    "message": f"Missing value {str(e)}",
                }
            )
        except (TypeError, JSONDecodeError):
            await self.send_json(
                {
                    "event": SCAN_EVENT_TYPES.SCAN_SETUP.value,
                    "status": False,
                    "message": "Message(s) must be in json format",
                }
            )
        else:
            alias_msg, alias_name, alias_status = is_valid_alias(alias=alias)

            if alias_status:
                alias_msg, alias_name, alias_status = format_alias(
                    device=self.device, alias=alias_name
                )

                if alias_status:
                    # add the device alias to device:alias & alias:device hashes
                    # in redis store
                    redis_client.hset(self.device_alias, key=self.device, value=alias_name)
                    redis_client.hset(self.alias_device, key=alias_name, value=self.device)

                    # connection time-to-live date object
                    ttl = timezone.now() + timezone.timedelta(hours=2)

                    # in redis store, update device data ttl value. And also set an expire
                    # option to the device data in redis store using the ttl as the value.
                    redis_client.hset(self.device, key="ttl", value=ttl.timestamp())
                    redis_client.expireat(self.device, ttl)

                    # SUCCESS: notify scanned device.
                    await self.channel_layer.send(
                        redis_client.hget(self.device, key="channel"),
                        {
                            "type": "chat.message",
                            "data": {
                                "event": SCAN_EVENT_TYPES.SCAN_SETUP.value,
                                "status": True,
                                "message": alias_msg,
                                "data": convert_array_to_dict(
                                    LuaScripts.get_device_data(
                                        keys=[self.device],
                                        client=redis_client,
                                    )
                                ),
                            },
                        },
                    )

            # SUCCESS | FAILURE: notify scanning device
            await self.send_json(
                {
                    "event": SCAN_EVENT_TYPES.SCAN_SETUP.value,
                    "status": alias_status,
                    "message": alias_msg,
                    "data": {"alias": alias_name},
                }
            )

            if alias_status:  # gracefully disconnect the scanning device
                await self.close(code=1000)

    async def chat_message(self, event):
        await self.send_json(event["data"])
