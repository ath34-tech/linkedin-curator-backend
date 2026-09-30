import httpx
import datetime
from typing import List
from app.sources.base import BaseSource, RawSignal

class GitHubSource(BaseSource):
    def __init__(self):
        super().__init__(name="github", source_type="api")
        self.endpoint = "https://api.github.com/search/repositories"

    async def fetch(self, limit: int = 25) -> List[RawSignal]:
        signals: List[RawSignal] = []
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "ATH-Radar-Agent"
        }
        
        # Look for recently updated or created repositories in AI/Dev tools
        cutoff_date = (datetime.datetime.utcnow() - datetime.timedelta(days=14)).strftime("%Y-%m-%d")
        query = f"stars:>30 pushed:>{cutoff_date} ai in:name,description,topics"

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                self.endpoint,
                headers=headers,
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": min(limit, 30)
                }
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("items", [])

            for item in items:
                name = item.get("full_name") or item.get("name")
                desc = item.get("description") or "Open source developer repository"
                url = item.get("html_url")
                stars = float(item.get("stargazers_count") or 0)
                forks = int(item.get("forks_count") or 0)
                topics = item.get("topics", [])
                language = item.get("language")
                if language and language not in topics:
                    topics.append(language.lower())

                pushed_at = None
                if item.get("pushed_at"):
                    try:
                        pushed_at = datetime.datetime.fromisoformat(item["pushed_at"].replace("Z", "+00:00"))
                        if getattr(pushed_at, "tzinfo", None) is not None:
                            pushed_at = pushed_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
                    except Exception:
                        pushed_at = datetime.datetime.utcnow()

                title = f"{name}: {desc[:100]}" if desc else name

                signals.append(
                    RawSignal(
                        title=title,
                        url=url,
                        source=self.name,
                        author=item.get("owner", {}).get("login"),
                        published_at=pushed_at or datetime.datetime.utcnow(),
                        summary=f"⭐ {int(stars)} stars. {desc}",
                        content=f"GitHub repository {name}. Primary language: {language}. Topics: {', '.join(topics)}. Description: {desc}",
                        topics=topics,
                        source_type=self.source_type,
                        raw_score=stars,
                        comment_count=forks
                    )
                )

        return signals
