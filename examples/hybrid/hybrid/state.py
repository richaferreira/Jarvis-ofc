"""Typed domain state; raw driver data is normalized at adapter boundaries."""

from typing import Literal, TypedDict


class VectorHit(TypedDict):
    document_id: str
    entity_id: str | None
    text: str
    distance: float


class GraphHit(TypedDict):
    panel: str
    circuit: str
    circuit_name: str
    device_id: str
    entity_id: str
    room: str
    protection_verified: bool


class DeviceSnapshot(TypedDict):
    device_id: str
    state: str
    observed_at: str
    received_at: str
    stale: bool
    broker_connected: bool
    retained: bool


class HybridState(TypedDict):
    owner: str
    query: str
    entity_ids: list[str]
    intent: Literal["conversation", "semantic", "topology", "live", "hybrid"]
    vector_context: list[VectorHit]
    graph_context: list[GraphHit]
    device_context: list[DeviceSnapshot]
    warnings: list[str]
    answer: str
