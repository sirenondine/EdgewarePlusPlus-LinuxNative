# Copyright (C) 2024 Araten & Marigold
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

# Intiface/Buttplug sex-toy support. Ported from upstream PR #220 by Close2real.
# The toy is driven over a websocket by Intiface Central (a separate app the user
# runs); buttplug-py speaks the protocol. This module is GUI-agnostic — it runs
# its own asyncio loop in a daemon thread and is poked from the GTK main thread.

import asyncio
import logging
import random
import time
from threading import Thread
from typing import TypedDict

# buttplug-py is an optional dependency. If it isn't installed the feature
# degrades gracefully: Sextoy can still be constructed but never connects.
try:
    from buttplug import Client, ProtocolSpec, WebsocketConnector
    from buttplug.client import Actuator
    BUTTPLUG_AVAILABLE = True
except Exception:
    Client = ProtocolSpec = WebsocketConnector = Actuator = None
    BUTTPLUG_AVAILABLE = False


class StoredActuator(TypedDict):
    speed: float
    clockwise: bool | None


class Sextoy:
    def __init__(self, settings) -> None:
        self.connected = False
        self._settings = settings
        self._loop = asyncio.new_event_loop()
        Thread(target=self._run_loop, daemon=True).start()
        self._client = Client("EdgewarePP", ProtocolSpec.v3) if BUTTPLUG_AVAILABLE else None
        # Continuous (held) forces, and per-session one-shot actuator state.
        self._continuous_forces: dict[int, float] = {}
        self._active_vibrations: dict[int, dict[int, StoredActuator]] = {}
        self._active_rotations: dict[int, dict[int, StoredActuator]] = {}
        self.vibration_index = 0
        self.rotation_index = 0

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    @property
    def connection_status(self) -> str:
        return "connected" if self.connected else "disconnected"

    def _address(self) -> str:
        raw = self._settings.initface_address
        return raw.get() if hasattr(raw, "get") else raw

    # ------------------------------------------------------------------
    # Connection
    def connect(self):
        """Connect + start scanning. Returns a concurrent.futures.Future, or
        None if already connected / buttplug unavailable."""
        if not BUTTPLUG_AVAILABLE:
            logging.warning("buttplug-py not installed; sex-toy support disabled.")
            return None
        if self.connected:
            logging.info("Sextoy already connected.")
            return None
        self._connector = WebsocketConnector(self._address(), logger=self._client.logger)
        return asyncio.run_coroutine_threadsafe(self._connect_and_scan(), self._loop)

    async def _connect_and_scan(self) -> None:
        try:
            await self._client.connect(self._connector)
            self.connected = True
            logging.info("Connected to Intiface.")
            self._loop.create_task(self._scan_loop())
        except Exception as e:
            logging.error(f"Sextoy connection error: {e}")
            self.connected = False
            raise

    async def _scan_loop(self, scan_duration: float = 3.0, interval: float = 2.0) -> None:
        while self.connected:
            try:
                await self._client.start_scanning()
                await asyncio.sleep(scan_duration)
                await self._client.stop_scanning()
            except Exception as e:
                logging.warning(f"Sextoy scan error: {e}")
            await asyncio.sleep(interval)

    @property
    def devices(self):
        return self._client.devices if self._client else {}

    def disconnect(self) -> None:
        if not self.connected:
            return

        async def _do_disconnect():
            await self._client.disconnect()
            self.connected = False

        asyncio.run_coroutine_threadsafe(_do_disconnect(), self._loop)

    # ------------------------------------------------------------------
    # One-shot vibration (skipped if a continuous force is held)
    async def _run_actuator(self, act, speed: float, duration: float,
                            device_index: int, clockwise=None) -> None:
        try:
            idx = act.index
            if clockwise is None:
                store, session_idx = self._active_vibrations, self.vibration_index
            else:
                store, session_idx = self._active_rotations, self.rotation_index

            store.setdefault(device_index, {})
            store[device_index].setdefault(session_idx, {})
            store[device_index][session_idx][idx] = {
                "act": act, "speed": speed, "clockwise": clockwise,
            }

            cmd = act.command if clockwise is None else (lambda sp: act.command(sp, clockwise))
            t0 = time.monotonic()
            asyncio.run_coroutine_threadsafe(cmd(speed), self._loop)

            remaining = duration - (time.monotonic() - t0)
            if remaining > 0:
                await asyncio.sleep(remaining)

            session = store[device_index].get(session_idx, {})
            session.pop(idx, None)
            if not session:
                store[device_index].pop(session_idx, None)
            if not store[device_index]:
                store.pop(device_index, None)

            # Find the most recent command for this actuator in other sessions.
            candidate_info = None
            candidate_session_id = None
            for session_id, session_dict in store.get(device_index, {}).items():
                if session_id == session_idx:
                    continue
                if idx in session_dict:
                    if candidate_session_id is None or session_id > candidate_session_id:
                        candidate_session_id = session_id
                        candidate_info = session_dict[idx]

            if device_index in self._continuous_forces:
                return

            if candidate_info is not None:
                real_act = candidate_info["act"]
                spd = candidate_info["speed"]
                cw = candidate_info["clockwise"]
                cmd_func = real_act.command if cw is None else (lambda s, cw=cw: real_act.command(s, cw))
                asyncio.run_coroutine_threadsafe(cmd_func(spd), self._loop)
            else:
                if clockwise is None:
                    asyncio.run_coroutine_threadsafe(act.command(0), self._loop)
                else:
                    asyncio.run_coroutine_threadsafe(act.command(0, clockwise), self._loop)
        except Exception as e:
            logging.error(f"Sextoy actuator error dev={device_index}: {e}")

    async def _vibrate_once(self, device_index: int, speed: float, duration: float) -> None:
        if device_index in self._continuous_forces:
            return
        dev = self._client.devices.get(device_index)
        if not dev:
            logging.warning(f"vibrate_once: device {device_index} not found")
            return

        if dev.actuators:
            self.vibration_index += 1
            for act in dev.actuators:
                asyncio.run_coroutine_threadsafe(
                    self._run_actuator(act, speed, duration, device_index), self._loop)

        if dev.rotatory_actuators:
            clockwise = bool(random.getrandbits(1))
            self.rotation_index += 1
            for rot in dev.rotatory_actuators:
                asyncio.run_coroutine_threadsafe(
                    self._run_actuator(rot, speed, duration, device_index, clockwise=clockwise),
                    self._loop)

    def vibrate(self, device_index: int, speed: float, duration: float = 1.0) -> None:
        if not self.connected:
            return
        asyncio.run_coroutine_threadsafe(
            self._vibrate_once(device_index, speed, duration), self._loop)

    # ------------------------------------------------------------------
    # Continuous (held) vibration
    async def _send_continuous_start(self, device_index: int, speed: float) -> None:
        dev = self._client.devices.get(device_index)
        if not dev:
            return
        clockwise = bool(random.getrandbits(1))
        for act in dev.actuators:
            await act.command(speed)
        for rot in dev.rotatory_actuators:
            await rot.command(speed, clockwise)

    def start_vibration(self, device_index: int, speed: float) -> None:
        if not self.connected or device_index in self._continuous_forces:
            return
        self._continuous_forces[device_index] = speed
        asyncio.run_coroutine_threadsafe(
            self._send_continuous_start(device_index, speed), self._loop)

    async def _send_continuous_stop(self, device_index: int) -> None:
        dev = self._client.devices.get(device_index)
        if not dev:
            return
        for act in dev.actuators:
            await act.command(0)
        for rot in dev.rotatory_actuators:
            await rot.command(0, bool(random.getrandbits(1)))

    def stop_vibration(self, device_index: int) -> None:
        if not self.connected or device_index not in self._continuous_forces:
            return
        self._continuous_forces.pop(device_index, None)
        asyncio.run_coroutine_threadsafe(
            self._send_continuous_stop(device_index), self._loop)

    # ------------------------------------------------------------------
    def list_devices(self) -> None:
        for idx, dev in self.devices.items():
            logging.info(f"[{idx}] {dev} - channels: {len(dev.actuators)}")
