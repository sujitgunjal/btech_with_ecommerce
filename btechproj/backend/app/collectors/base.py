"""Abstract base class for telemetry collectors."""

from abc import ABC, abstractmethod
from datetime import datetime

from ..schemas.evidence import NormalizedEvent


class BaseCollector(ABC):
    """Abstract base class for all telemetry collectors.

    Each collector retrieves data from a specific observability system,
    normalizes it into NormalizedEvent instances, and returns them for
    storage as investigation evidence.
    """

    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @abstractmethod
    async def collect(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[NormalizedEvent]:
        """Collect and normalize telemetry events for a service."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the telemetry source is reachable."""
        ...
