# Copyright (C) 2025 Araten & Marigold
#
# This file is part of Edgeware++.
#
# Edgeware++ is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Edgeware++ is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Edgeware++.  If not, see <https://www.gnu.org/licenses/>.

# A small, self-contained Buttplug v3 client — speaks the JSON-over-websocket
# protocol to Intiface Central directly, replacing the unmaintained buttplug-py
# dependency. Intiface still owns the device layer (BLE + the per-toy protocols);
# we only own the client side of the wire protocol.
#
# The public surface deliberately matches the slice of buttplug-py that
# features/sextoy.py uses, so that module needs only to change its import:
#   Client(name, ProtocolSpec.v3) -> .connect(WebsocketConnector(addr)),
#   .disconnect(), .start_scanning(), .stop_scanning(), .connected, .devices
#   Device.actuators / .rotatory_actuators ; Actuator.index, .command(scalar[, cw])
#
# All coroutines run on the caller's asyncio loop (sextoy.py owns a loop in a
# daemon thread). A single reader task dispatches replies (by message Id) and
# events (DeviceAdded/DeviceRemoved/ScanningFinished).

import asyncio
import json
import logging

# Protocol message version we speak.
_MESSAGE_VERSION = 3


class ProtocolSpec:
    v3 = 3


class WebsocketConnector:
    """Holds the websocket address. logger is accepted for buttplug-py parity."""

    def __init__(self, address: str, logger=None) -> None:
        self.address = address
        self.logger = logger


class Actuator:
    """One scalar (vibrate/oscillate/...) or rotatory actuator on a device.
    command(scalar) sends a ScalarCmd; rotatory actuators take (speed, clockwise)
    and send a RotateCmd."""

    def __init__(self, client: "Client", device_index: int, index: int,
                 actuator_type: str, descriptor: str = "", step_count: int = 0,
                 rotatory: bool = False) -> None:
        self._client = client
        self._device_index = device_index
        self.index = index
        self.actuator_type = actuator_type
        self.descriptor = descriptor
        self.step_count = step_count
        self._rotatory = rotatory

    async def command(self, scalar: float, clockwise: bool = True) -> None:
        scalar = max(0.0, min(1.0, float(scalar)))
        if self._rotatory:
            await self._client._send_no_wait({
                "RotateCmd": {
                    "Id": self._client._next_id(),
                    "DeviceIndex": self._device_index,
                    "Rotations": [{"Index": self.index, "Speed": scalar, "Clockwise": bool(clockwise)}],
                }
            })
        else:
            await self._client._send_no_wait({
                "ScalarCmd": {
                    "Id": self._client._next_id(),
                    "DeviceIndex": self._device_index,
                    "Scalars": [{"Index": self.index, "Scalar": scalar, "ActuatorType": self.actuator_type}],
                }
            })


class Device:
    def __init__(self, client: "Client", entry: dict) -> None:
        self._client = client
        self.name = entry.get("DeviceName", "Device")
        self.index = entry["DeviceIndex"]
        messages = entry.get("DeviceMessages", {})
        self.actuators = [
            Actuator(client, self.index, i,
                     attr.get("ActuatorType", "Vibrate"),
                     attr.get("FeatureDescriptor", ""),
                     attr.get("StepCount", 0))
            for i, attr in enumerate(messages.get("ScalarCmd", []))
        ]
        self.rotatory_actuators = [
            Actuator(client, self.index, i,
                     attr.get("ActuatorType", "Rotate"),
                     attr.get("FeatureDescriptor", ""),
                     attr.get("StepCount", 0), rotatory=True)
            for i, attr in enumerate(messages.get("RotateCmd", []))
        ]

    def __str__(self) -> str:
        return self.name


class Client:
    def __init__(self, name: str, spec=ProtocolSpec.v3) -> None:
        self.name = name
        self.logger = logging.getLogger("buttplug")
        self.devices: dict[int, Device] = {}
        self.connected = False
        self._ws = None
        self._reader = None
        self._pinger = None
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    # ------------------------------------------------------------------
    async def connect(self, connector: WebsocketConnector) -> None:
        from websockets.asyncio.client import connect as ws_connect
        self._ws = await ws_connect(connector.address, max_size=None)
        self.connected = True
        self._reader = asyncio.ensure_future(self._read_loop())

        info = await self._request({"RequestServerInfo": {
            "Id": self._next_id(), "ClientName": self.name,
            "MessageVersion": _MESSAGE_VERSION}})
        ping_ms = (info.get("ServerInfo", {}) or {}).get("MaxPingTime", 0)

        dl = await self._request({"RequestDeviceList": {"Id": self._next_id()}})
        for entry in (dl.get("DeviceList", {}) or {}).get("Devices", []):
            self.devices[entry["DeviceIndex"]] = Device(self, entry)

        if ping_ms and ping_ms > 0:
            self._pinger = asyncio.ensure_future(self._ping_loop(ping_ms / 1000.0))

    async def disconnect(self) -> None:
        self.connected = False
        for task in (self._reader, self._pinger):
            if task:
                task.cancel()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None
        self.devices.clear()

    async def start_scanning(self) -> None:
        await self._request({"StartScanning": {"Id": self._next_id()}})

    async def stop_scanning(self) -> None:
        await self._request({"StopScanning": {"Id": self._next_id()}})

    # ------------------------------------------------------------------
    async def _request(self, message: dict) -> dict:
        """Send a message and await the reply with the matching Id."""
        msg_id = next(iter(message.values()))["Id"]
        future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        await self._ws.send(json.dumps([message]))
        try:
            return await asyncio.wait_for(future, timeout=10)
        finally:
            self._pending.pop(msg_id, None)

    async def _send_no_wait(self, message: dict) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps([message]))
        except Exception as e:
            self.logger.debug(f"buttplug send failed: {e}")

    async def _ping_loop(self, max_interval: float) -> None:
        interval = max(0.5, max_interval / 2)
        try:
            while self.connected:
                await self._send_no_wait({"Ping": {"Id": self._next_id()}})
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    messages = json.loads(raw)
                except Exception:
                    continue
                for wrapper in messages:
                    for name, body in wrapper.items():
                        self._dispatch(name, body)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.info(f"buttplug read loop ended: {e}")
        finally:
            self.connected = False

    def _dispatch(self, name: str, body: dict) -> None:
        msg_id = body.get("Id", 0)
        # Replies to our requests resolve the pending future.
        if msg_id and msg_id in self._pending:
            future = self._pending[msg_id]
            if not future.done():
                if name == "Error":
                    future.set_exception(RuntimeError(body.get("ErrorMessage", "Buttplug error")))
                else:
                    future.set_result({name: body})
            return
        # Otherwise it's a server event.
        if name == "DeviceAdded":
            self.devices[body["DeviceIndex"]] = Device(self, body)
        elif name == "DeviceRemoved":
            self.devices.pop(body.get("DeviceIndex"), None)
