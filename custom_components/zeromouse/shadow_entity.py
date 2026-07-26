"""Shared optimistic-state handling for entities that write to a backend
which doesn't confirm changes synchronously.

Two of ZeroMouse's write paths have this problem for different reasons:
- Shadow writes (PATCH to 'desired') aren't applied by the device until
  it next processes the MQTT delta and reports back - can take a few
  seconds, sometimes longer if the device is briefly offline.
- Even the GraphQL mutation path, while faster, has no hard real-time
  guarantee that a refresh immediately after a write reflects it.

Without this, a toggle would flicker back to its old value for a few
seconds after every flip (or worse, revert entirely if a poll happens to
land in that gap). This mixin remembers what was just commanded and
keeps showing that until the coordinator's actual data confirms it, at
which point it steps out of the way and defers back to live data."""
from __future__ import annotations

from typing import Any, Awaitable, Callable


class OptimisticMixin:
    """Mix into a CoordinatorEntity subclass alongside the entity
    platform's base class (SwitchEntity, NumberEntity, etc)."""

    def __init__(self) -> None:
        self._pending_value: Any = None

    def _resolve(self, actual: Any) -> Any:
        """Given the coordinator's current real value, return what
        should actually be shown - the pending write if one hasn't been
        confirmed yet, otherwise the real value."""
        if self._pending_value is not None:
            if actual == self._pending_value:
                self._pending_value = None  # confirmed - stop overriding
            else:
                return self._pending_value
        return actual

    async def _write_and_hold(
        self, value: Any, write_coro: Awaitable[None]
    ) -> None:
        """Send the write, remember it as pending so the UI reflects the
        commanded value immediately rather than waiting on a slow
        backend, then await the actual write (which should trigger a
        coordinator refresh on its own)."""
        self._pending_value = value
        self.async_write_ha_state()
        await write_coro
