import httpx
import feedparser
import datetime
from typing import List
from app.sources.base import BaseSource, RawSignal

class ArxivSource(BaseSource):
    def __init__(self):
        super().__init__(name="arxiv", source_type="api")
        self.endpoint = "https://export.arxiv.org/api/query"

    async def fetch(self, limit: int = 25) -> List[RawSignal]:
        signals: List[RawSignal] = []
        # Search recent papers in Artificial Intelligence, Learning, and Software Engineering
        query = "cat:cs.AI OR cat:cs.LG OR cat:cs.SE"

        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            response = await client.get(
                self.endpoint,
                params={
                    "search_query": query,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                    "max_results": limit
                }
            )
            response.raise_for_status()
            feed = feedparser.parse(response.text)

            for entry in feed.entries:
                title = entry.get("title", "").replace("\n", " ").strip()
                url = entry.get("link", "")
                summary = entry.get("summary", "").replace("\n", " ").strip()
                author = entry.get("author", "arXiv Researcher")
                
                # Categories / tags
                topics = [tag.get("term") for tag in entry.get("tags", []) if tag.get("term")]

                published_at = datetime.datetime.utcnow()
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published_at = datetime.datetime(*entry.published_parsed[:6])
                    except Exception:
                        pass

                signals.append(
                    RawSignal(
                        title=title,
                        url=url,
                        source=self.name,
                        author=author,
                        published_at=published_at,
                        summary=summary[:600] + ("..." if len(summary) > 600 else ""),
                        content=summary,
                        topics=topics,
                        source_type=self.source_type,
                        raw_score=10.0,  # Base citation/peer value
                        comment_count=0
                    )
                )

        return signals
