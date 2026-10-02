import httpx
import feedparser
import datetime
from typing import List, Dict
from app.sources.base import BaseSource, RawSignal

DEFAULT_FEEDS = [
    {"name": "Simon Willison Weblog", "url": "https://simonwillison.net/atom/everything/"},
    {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "GitHub Blog", "url": "https://github.blog/feed/"},
    {"name": "Cloudflare Engineering", "url": "https://blog.cloudflare.com/rss/"},
    {"name": "The Pragmatic Engineer", "url": "https://newsletter.pragmaticengineer.com/feed"},
    {"name": "Latent Space", "url": "https://www.latent.space/feed"},
    {"name": "Martin Fowler", "url": "https://martinfowler.com/feed.atom"},
]

class RSSFeedSource(BaseSource):
    def __init__(self, feeds: List[Dict[str, str]] = None):
        super().__init__(name="rss", source_type="rss")
        self.feeds = feeds or DEFAULT_FEEDS

    async def fetch(self, limit: int = 30) -> List[RawSignal]:
        signals: List[RawSignal] = []

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for feed_info in self.feeds:
                try:
                    resp = await client.get(
                        feed_info["url"],
                        headers={"User-Agent": "ATH-Radar-Agent"}
                    )
                    if resp.status_code != 200:
                        continue

                    parsed = feedparser.parse(resp.text)
                    for entry in parsed.entries[:10]:
                        title = entry.get("title", "").strip()
                        url = entry.get("link", "")
                        if not title or not url:
                            continue

                        summary = entry.get("summary", "") or entry.get("description", "")
                        # Strip html tags simply if present
                        import re
                        clean_summary = re.sub(r'<[^>]+>', '', summary).strip()[:600]

                        published_at = datetime.datetime.utcnow()
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            try:
                                published_at = datetime.datetime(*entry.published_parsed[:6])
                            except Exception:
                                pass

                        topics = [t.get("term") for t in entry.get("tags", []) if t.get("term")]
                        topics.append(feed_info["name"].lower())

                        signals.append(
                            RawSignal(
                                title=title,
                                url=url,
                                source=f"rss:{feed_info['name']}",
                                author=entry.get("author") or feed_info["name"],
                                published_at=published_at,
                                summary=clean_summary,
                                content=clean_summary,
                                topics=topics,
                                source_type=self.source_type,
                                raw_score=5.0,
                                comment_count=0
                            )
                        )
                except Exception:
                    continue

        return signals[:limit]
