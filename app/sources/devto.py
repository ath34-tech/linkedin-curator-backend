import httpx
import datetime
from typing import List
from app.sources.base import BaseSource, RawSignal

class DevToSource(BaseSource):
    def __init__(self):
        super().__init__(name="devto", source_type="api")
        self.endpoint = "https://dev.to/api/articles"

    async def fetch(self, limit: int = 25) -> List[RawSignal]:
        signals: List[RawSignal] = []
        tags = ["ai", "python", "architecture", "devops"]

        async with httpx.AsyncClient(timeout=15.0) as client:
            for tag in tags:
                try:
                    response = await client.get(
                        self.endpoint,
                        params={"tag": tag, "top": 7, "per_page": 10}
                    )
                    if response.status_code != 200:
                        continue
                    articles = response.json()
                    for art in articles:
                        url = art.get("url")
                        title = art.get("title")
                        if not url or not title:
                            continue

                        published_at = datetime.datetime.utcnow()
                        if art.get("published_at"):
                            try:
                                dt = datetime.datetime.fromisoformat(art["published_at"].replace("Z", "+00:00"))
                                published_at = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
                            except Exception:
                                pass

                        reactions = float(art.get("positive_reactions_count") or 0)
                        comments = int(art.get("comments_count") or 0)
                        summary = art.get("description") or title
                        tag_list = art.get("tag_list", [])

                        signals.append(
                            RawSignal(
                                title=title,
                                url=url,
                                source=self.name,
                                author=art.get("user", {}).get("name"),
                                published_at=published_at,
                                summary=summary,
                                content=summary,
                                topics=tag_list,
                                source_type=self.source_type,
                                raw_score=reactions,
                                comment_count=comments
                            )
                        )
                except Exception:
                    continue

        return signals[:limit]
