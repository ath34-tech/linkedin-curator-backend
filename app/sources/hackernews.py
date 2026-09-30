import httpx
import datetime
from typing import List
from app.sources.base import BaseSource, RawSignal

class HackerNewsSource(BaseSource):
    def __init__(self):
        super().__init__(name="hackernews", source_type="api")
        # Algolia HN search API provides rich data in a single fast query
        self.endpoint = "https://hn.algolia.com/api/v1/search_by_date"

    async def fetch(self, limit: int = 30) -> List[RawSignal]:
        signals: List[RawSignal] = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Query top stories with tech/AI relevance
            response = await client.get(
                self.endpoint,
                params={
                    "tags": "story",
                    "numericFilters": "points>15",
                    "hitsPerPage": limit
                }
            )
            response.raise_for_status()
            data = response.json()
            hits = data.get("hits", [])

            for hit in hits:
                title = hit.get("title")
                url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                if not title or not url:
                    continue

                created_at = None
                if hit.get("created_at"):
                    try:
                        dt = datetime.datetime.fromisoformat(hit["created_at"].replace("Z", "+00:00"))
                        created_at = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
                    except Exception:
                        created_at = datetime.datetime.utcnow()

                author = hit.get("author")
                points = float(hit.get("points") or 0)
                comments = int(hit.get("num_comments") or 0)
                story_text = hit.get("story_text") or ""

                # Extract basic tags
                tags = [t for t in hit.get("_tags", []) if t not in ("story", "author_" + (author or ""))]

                signals.append(
                    RawSignal(
                        title=title,
                        url=url,
                        source=self.name,
                        author=author,
                        published_at=created_at or datetime.datetime.utcnow(),
                        summary=story_text[:500] if story_text else f"Hacker News story with {int(points)} points and {comments} comments.",
                        content=story_text,
                        topics=tags,
                        source_type=self.source_type,
                        raw_score=points,
                        comment_count=comments
                    )
                )

        return signals
