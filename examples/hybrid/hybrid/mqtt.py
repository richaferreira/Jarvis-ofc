"""MQTT subscription, latest-state cache and bounded per-subscriber event queues."""

import asyncio
import logging
import random
import ssl
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import aiomqtt
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from hybrid.settings import Settings
from hybrid.state import DeviceSnapshot

log = logging.getLogger(__name__)


class DeviceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    event_id: UUID
    device_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    state: str = Field(pattern=r"^(on|off|unavailable)$")
    observed_at: AwareDatetime


class StateHub:
    def __init__(self, allowed: list[str], ttl: float) -> None:
        self.allowed, self.ttl = frozenset(allowed), ttl
        self.connected = False
        self._latest: dict[str, tuple[DeviceEvent, float, str, bool]] = {}
        self._listeners: set[asyncio.Queue[DeviceSnapshot]] = set()

    def accept(self, event: DeviceEvent, retained: bool) -> bool:
        if event.device_id not in self.allowed:
            return False
        now = datetime.now(UTC)
        if (event.observed_at - now).total_seconds() > 5:
            return False  # Relógio inválido não pode criar estado eternamente "novo".
        old = self._latest.get(event.device_id)
        if old and (old[0].event_id == event.event_id or old[0].observed_at >= event.observed_at):
            return False  # QoS 1 admite duplicatas; estados antigos não sobrescrevem os novos.
        self._latest[event.device_id] = (event, time.monotonic(), now.isoformat(), retained)
        snapshot = self.snapshot([event.device_id])[0]
        for queue in self._listeners:
            if queue.full():
                queue.get_nowait()  # Canal de latest-state; não é trilha de auditoria.
            queue.put_nowait(snapshot)
        return True

    def snapshot(self, device_ids: list[str] | None = None) -> list[DeviceSnapshot]:
        selected = self.allowed if device_ids is None else self.allowed.intersection(device_ids)
        snapshots: list[DeviceSnapshot] = []
        for device in sorted(selected):
            data = self._latest.get(device)
            if data is None:
                snapshots.append({"device_id": device, "state": "unknown", "observed_at": "",
                                  "received_at": "", "stale": True,
                                  "broker_connected": self.connected, "retained": False})
                continue
            event, received_mono, received_at, retained = data
            age = max(time.monotonic() - received_mono,
                      (datetime.now(UTC) - event.observed_at).total_seconds())
            snapshots.append({"device_id": device, "state": event.state,
                              "observed_at": event.observed_at.isoformat(), "received_at": received_at,
                              "stale": age > self.ttl or not self.connected or event.state == "unavailable",
                              "broker_connected": self.connected, "retained": retained})
        return snapshots

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[DeviceSnapshot]]:
        queue: asyncio.Queue[DeviceSnapshot] = asyncio.Queue(maxsize=32)
        self._listeners.add(queue)
        try:
            yield queue
        finally:
            self._listeners.discard(queue)


class MQTTService:
    """Uma instância por lifespan, por injeção de dependência, sem Singleton global."""

    def __init__(self, settings: Settings, hub: StateHub) -> None:
        self.settings, self.hub = settings, hub

    async def run(self) -> None:
        delay = 1.0
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=self.settings.mqtt_host, port=self.settings.mqtt_port,
                    username=self.settings.mqtt_user,
                    password=self.settings.mqtt_password.get_secret_value(),
                    identifier=f"jarvis-{self.settings.owner}", timeout=10,
                    max_queued_incoming_messages=256,
                    tls_context=ssl.create_default_context() if self.settings.mqtt_tls else None,
                ) as client:
                    for device in self.settings.mqtt_device_ids:
                        await client.subscribe(f"jarvis/{self.settings.owner}/devices/{device}/state", qos=1)
                    self.hub.connected = True
                    delay = 1.0
                    async for message in client.messages:
                        try:
                            payload = message.payload
                            if not isinstance(payload, (bytes, bytearray)) or len(payload) > 4096:
                                continue
                            event = DeviceEvent.model_validate_json(payload)
                            expected = f"jarvis/{self.settings.owner}/devices/{event.device_id}/state"
                            if str(message.topic) == expected:
                                self.hub.accept(event, message.retain)
                        except (ValidationError, ValueError):
                            log.warning("invalid_mqtt_event")
            except aiomqtt.MqttError:
                log.warning("mqtt_disconnected")
            finally:
                self.hub.connected = False
            await asyncio.sleep(delay + random.uniform(0, delay * 0.2))
            delay = min(delay * 2, 30)
