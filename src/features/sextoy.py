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
import math
import random
import time
from threading import Thread
from typing import TypedDict


# Vibration patterns: f(t_seconds, period_seconds) -> intensity multiplier 0..1.
# The device's summed continuous total is multiplied by this each tick.
def _p_constant(t: float, period: float) -> float:
    return 1.0


def _p_pulse(t: float, period: float) -> float:
    return 1.0 if (t % period) < period / 2 else 0.0


def _p_wave(t: float, period: float) -> float:
    return 0.5 + 0.5 * math.sin(2 * math.pi * t / period)


def _p_ramp(t: float, period: float) -> float:
    return (t % period) / period


def _p_random(t: float, period: float) -> float:
    # Steps to a new random level every quarter-period (deterministic per step).
    step = int(t / (period / 4)) if period else 0
    return (math.sin(step * 12.9898) * 43758.5453) % 1.0


PATTERNS = {
    "constant": _p_constant,
    "pulse": _p_pulse,
    "wave": _p_wave,
    "ramp": _p_ramp,
    "random": _p_random,
}
PATTERN_NAMES = list(PATTERNS.keys())

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
        # Called with the new bool whenever the connection state changes
        # (connect / disconnect / dropped). Wired by misc to notifications + tray.
        # Invoked from the asyncio thread; the callback must marshal to the GTK
        # main thread itself.
        self.on_status_change = None
        self._settings = settings
        self._loop = asyncio.new_event_loop()
        Thread(target=self._run_loop, daemon=True).start()
        self._client = Client("EdgewarePP", ProtocolSpec.v3) if BUTTPLUG_AVAILABLE else None
        # Continuous contributions: device -> {token: force}. Each open
        # continuous popup is one token; the device runs at the summed total
        # (capped at 1.0) so concurrent popups stack. Plus one-shot state.
        self._contributions: dict[int, dict[str, float]] = {}
        # Per-device pattern (name, period seconds) and running modulation task.
        self._patterns: dict[int, tuple[str, float]] = {}
        self._modulation: dict[int, object] = {}
        # Transient one-shot "boost" riding the continuous loop: device -> (end_time, force).
        # Lets a timed pulse (e.g. image open) bump above the continuous baseline
        # for its duration, then settle back, instead of being suppressed.
        self._boost: dict[int, tuple[float, float]] = {}
        self._active_vibrations: dict[int, dict[int, StoredActuator]] = {}
        self._active_rotations: dict[int, dict[int, StoredActuator]] = {}
        self.vibration_index = 0
        self.rotation_index = 0

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _set_connected(self, value: bool) -> None:
        """Update connection state and fire on_status_change on transitions."""
        if value == self.connected:
            return
        self.connected = value
        if self.on_status_change:
            try:
                self.on_status_change(value)
            except Exception as e:
                logging.warning(f"Sextoy status callback error: {e}")

    @property
    def connection_status(self) -> str:
        return "connected" if self.connected else "disconnected"

    def _address(self) -> str:
        raw = self._settings.intiface_address
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

    def reconnect(self):
        """Reconnect after a drop (tray menu). No-op if already connected."""
        if self.connected:
            return None
        logging.info("Sextoy reconnect requested.")
        return self.connect()

    async def _connect_and_scan(self) -> None:
        try:
            await self._client.connect(self._connector)
            logging.info("Connected to Intiface.")
            self._set_connected(True)
            self._loop.create_task(self._scan_loop())
            self._loop.create_task(self._monitor_loop())
        except Exception as e:
            logging.error(f"Sextoy connection error: {e}")
            self._set_connected(False)
            raise

    async def _monitor_loop(self, interval: float = 3.0) -> None:
        """Detect a dropped websocket (Intiface closed, toy unplugged at the
        host, network blip) so the user gets a disconnect notification instead
        of silent failure."""
        while self.connected:
            await asyncio.sleep(interval)
            try:
                alive = self._client.connected
            except Exception:
                alive = False
            if not alive:
                logging.warning("Sextoy connection lost.")
                self._set_connected(False)
                break

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
            self._set_connected(False)

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

            if self._contributions.get(device_index):
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
        if self._contributions.get(device_index):
            # Continuous holds this device: instead of dropping the pulse, ride a
            # transient boost on top of the continuous baseline (e.g. a strong
            # bump on image open that then settles into a light continuous hum).
            self._boost[device_index] = (time.monotonic() + duration, speed)
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
    # Continuous (held) vibration — contributions stack into a per-device total,
    # modulated by the device's pattern via a ticking task.
    _TICK = 0.15  # seconds between pattern updates (~7/s, BLE-friendly)

    def set_pattern(self, device_index: int, name: str, period: float) -> None:
        if name not in PATTERNS:
            name = "constant"
        self._patterns[device_index] = (name, max(0.2, float(period)))

    async def _send(self, device_index: int, level: float) -> None:
        dev = self._client.devices.get(device_index)
        if not dev:
            return
        clockwise = bool(random.getrandbits(1))
        for act in dev.actuators:
            await act.command(level)
        for rot in dev.rotatory_actuators:
            await rot.command(level, clockwise)

    async def _modulate(self, device_index: int) -> None:
        t0 = time.monotonic()
        try:
            while self._contributions.get(device_index):
                now = time.monotonic()
                boost = self._boost.get(device_index)
                if boost and now < boost[0]:
                    # Hold the boost force flat (ignore the pattern) so the bump
                    # reads crisp, then fall back to the continuous baseline.
                    level = boost[1]
                else:
                    if boost:
                        self._boost.pop(device_index, None)
                    total = min(1.0, sum(self._contributions[device_index].values()))
                    name, period = self._patterns.get(device_index, ("constant", 2.0))
                    factor = PATTERNS.get(name, _p_constant)(now - t0, period)
                    level = total * factor
                await self._send(device_index, round(level, 3))
                await asyncio.sleep(self._TICK)
        finally:
            await self._send(device_index, 0.0)
            self._boost.pop(device_index, None)
            self._modulation.pop(device_index, None)

    def add_contribution(self, device_index: int, token: str, force: float) -> None:
        """Add a named force contribution; start the modulation loop if needed."""
        if not self.connected:
            return
        self._contributions.setdefault(device_index, {})[token] = force
        if device_index not in self._modulation:
            self._modulation[device_index] = asyncio.run_coroutine_threadsafe(
                self._modulate(device_index), self._loop)

    def remove_contribution(self, device_index: int, token: str) -> None:
        if not self.connected:
            return
        bucket = self._contributions.get(device_index)
        if not bucket or token not in bucket:
            return
        bucket.pop(token, None)
        if not bucket:
            self._contributions.pop(device_index, None)
            # The modulation loop sees the empty dict, sends 0 and exits.

    def remove_token(self, token: str) -> None:
        """Remove a contribution token from every device (used on popup close
        when we don't track which device it landed on)."""
        for device_index in list(self._contributions.keys()):
            self.remove_contribution(device_index, token)

    # ------------------------------------------------------------------
    def list_devices(self) -> None:
        for idx, dev in self.devices.items():
            logging.info(f"[{idx}] {dev} - channels: {len(dev.actuators)}")
