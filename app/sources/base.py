import abc
import datetime
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class RawSignal(BaseModel):
    title: str
    url: str
    source: str
    author: Optional[str] = None
    published_at: Optional[datetime.datetime] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    topics: List[str] = []
    source_type: str = "api"
    raw_score: float = 0.0
    comment_count: int = 0

class BaseSource(abc.ABC):
    def __init__(self, name: str, source_type: str = "api"):
        self.name = name
        self.source_type = source_type

    @abc.abstractmethod
    async def fetch(self, limit: int = 25) -> List[RawSignal]:
        """Fetch raw items from source and return list of normalized RawSignal objects."""
        pass

    async def safe_fetch(self, limit: int = 25) -> List[RawSignal]:
        """Wrap fetch with error boundary to prevent crashing pipeline on individual source failure."""
        try:
            signals = await self.fetch(limit=limit)
            logger.info(f"[{self.name}] successfully collected {len(signals)} signals")
            return signals
        except Exception as e:
            logger.error(f"[{self.name}] failed to fetch signals: {e}", exc_info=True)
            return []
