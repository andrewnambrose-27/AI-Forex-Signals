from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any


class CalendarProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    healthy: bool
    configured: bool
    message: str


class EconomicCalendarProvider(ABC):
    name: str

    @abstractmethod
    def fetch_events(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def normalize_event(self, raw_event: dict[str, Any]) -> Any:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> ProviderHealth:
        raise NotImplementedError
