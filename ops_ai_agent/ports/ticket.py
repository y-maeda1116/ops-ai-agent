"""チケット起票ポート。"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class TicketPort(Protocol):
    def create_ticket(self, title: str, description: str, *, severity: str) -> str: ...


@runtime_checkable
class TicketStorePort(Protocol):
    """重複起票防止のための起票済みフィンガープリント記録。"""

    def contains(self, fingerprint: str) -> bool: ...

    def record(self, fingerprint: str) -> None: ...
