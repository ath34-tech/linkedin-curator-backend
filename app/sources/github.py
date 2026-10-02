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
        
        # Query across diverse engineering domains: inference, dev tools, systems, agents, databases
        cutoff_date = (datetime.datetime.utcnow() - datetime.timedelta(days=14)).strftime("%Y-%m-%d")
        queries = [
            f"stars:>40 pushed:>{cutoff_date} (inference OR vllm OR llm OR gateway OR latency) in:name,description,topics",
            f"stars:>40 pushed:>{cutoff_date} (cli OR \"developer tool\" OR \"terminal\" OR benchmark) in:name,description,topics",
            f"stars:>40 pushed:>{cutoff_date} (agent OR \"tool use\" OR workflow OR local) in:name,description,topics",
            f"stars:>40 pushed:>{cutoff_date} (database OR sqlite OR vector OR cache OR rust) in:name,description,topics"
        ]
        import random
        # Pick 2 complementary queries per fetch
        chosen_queries = random.sample(queries, 2)

        async with httpx.AsyncClient(timeout=15.0) as client:
            items = []
            seen_repos = set()
            per_query_limit = max(10, limit // 2)

            for q in chosen_queries:
                try:
                    response = await client.get(
                        self.endpoint,
                        headers=headers,
                        params={
                            "q": q,
                            "sort": "stars",
                            "order": "desc",
                            "per_page": per_query_limit
                        }
                    )
                    if response.status_code == 200:
                        batch = response.json().get("items", [])
                        for b in batch:
                            if b.get("html_url") not in seen_repos:
                                seen_repos.add(b.get("html_url"))
                                items.append(b)
                except Exception:
                    continue

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
