from __future__ import annotations

from typing import Optional


class StreamPrinter:
    """
    Print incremental streaming output from a StateManager field.

    Use with StateManager.subscribe(StreamPrinter(...)).
    """

    def __init__(
        self,
        state_manager,
        key: str = "streaming_output",
        enabled: bool = True,
        flush: bool = True,
    ):
        self.state_manager = state_manager
        self.key = key
        self.enabled = enabled
        self.flush = flush
        self._last: str = ""

    def reset(self) -> None:
        self._last = ""

    def set_enabled(self, value: bool) -> None:
        self.enabled = value

    def __call__(self) -> None:
        if not self.enabled:
            return

        try:
            state = self.state_manager.get()
            current = getattr(state, self.key, "")
        except Exception:
            return

        if not current or current == self._last:
            return

        delta = current[len(self._last):]
        if delta:
            print(delta, end="", flush=self.flush)
        self._last = current


__all__ = ["StreamPrinter"]
