import asyncio
import logging
from typing import List
from app.sources.base import BaseSource, RawSignal
from app.sources.hackernews import HackerNewsSource
from app.sources.github import GitHubSource
from app.sources.arxiv import ArxivSource
from app.sources.devto import DevToSource
from app.sources.rss import RSSFeedSource

logger = logging.getLogger(__name__)

def get_default_sources() -> List[BaseSource]:
    return [
        HackerNewsSource(),
        GitHubSource(),
        ArxivSource(),
        DevToSource(),
        RSSFeedSource()
    ]

async def collect_all_sources(sources: List[BaseSource] = None) -> List[RawSignal]:
    """
    Collect from all sources concurrently with error boundaries.
    """
    active_sources = sources or get_default_sources()
    logger.info(f"[Sources] Starting collection across {len(active_sources)} sources...")

    tasks = [source.safe_fetch(limit=25) for source in active_sources]
    results = await asyncio.gather(*tasks)

    all_signals: List[RawSignal] = []
    for source_signals in results:
        all_signals.extend(source_signals)

    logger.info(f"[Sources] Collected total of {len(all_signals)} raw signals")
    return all_signals

def deduplicate_signals(signals: List[RawSignal]) -> List[RawSignal]:
    """
    Deduplicate signals by normalized URL and title similarity.
    """
    seen_urls = set()
    seen_titles = set()
    deduped: List[RawSignal] = []

    for sig in signals:
        norm_url = sig.url.strip().lower().rstrip("/")
        norm_title = "".join(ch for ch in sig.title.lower() if ch.isalnum())[:60]

        if norm_url in seen_urls or norm_title in seen_titles:
            continue

        seen_urls.add(norm_url)
        seen_titles.add(norm_title)
        deduped.append(sig)

    removed = len(signals) - len(deduped)
    logger.info(f"[Deduplication] removed {removed} duplicate signals; {len(deduped)} signals remaining")
    return deduped

__all__ = [
    "BaseSource", "RawSignal", "HackerNewsSource", "GitHubSource",
    "ArxivSource", "DevToSource", "RSSFeedSource",
    "get_default_sources", "collect_all_sources", "deduplicate_signals"
]
