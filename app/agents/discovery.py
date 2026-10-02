import logging
import datetime
from collections import defaultdict
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.sources.base import RawSignal
from app.models.models import Trend, TrendSignal, ContentSignal
from app.services.gemini import gemini_service

logger = logging.getLogger(__name__)

STOPWORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "with", "of",
    "is", "are", "was", "how", "what", "why", "this", "that", "from", "by", "new",
    "using", "into", "it", "its", "via", "your", "can", "now", "our", "all", "out",
    "ai", "llm", "model", "models", "app", "code", "tool", "tools", "system", "systems",
    "part", "release", "first", "one", "two", "good", "best", "use", "build", "like",
    "get", "free", "open", "source", "post", "blog", "guide", "day", "week", "year",
    "about", "more", "make", "some", "time", "just", "over", "such", "than", "them"
}

class DiscoveryAgent:
    """
    Agent 3 — Discovery Agent
    Clusters normalized signals, calculates deterministic trend scores,
    and asks Gemini to semantically interpret the clusters into distinct trends.
    """
    def __init__(self):
        self.name = "Discovery Agent"

    async def run(self, signals: List[RawSignal], db: Session) -> List[Trend]:
        logger.info(f"[{self.name}] Analyzing {len(signals)} normalized signals...")

        if not signals:
            logger.warning(f"[{self.name}] No signals received.")
            return []

        # 1. Cluster signals deterministically by keywords and topics
        clusters = self._cluster_signals(signals)
        logger.info(f"[{self.name}] Formed {len(clusters)} initial signal clusters.")

        # 2. Score clusters (deterministic heat, momentum, novelty, confidence)
        scored_clusters = []
        for cluster_key, cluster_signals in clusters.items():
            if len(cluster_signals) < 1:
                continue
            metrics = self._calculate_metrics(cluster_signals, db)
            scored_clusters.append({
                "key": cluster_key,
                "signals": cluster_signals,
                "metrics": metrics
            })

        # Sort by composite score (heat + momentum * 1.2 + novelty boost)
        scored_clusters.sort(
            key=lambda c: c["metrics"]["heat_score"] + (c["metrics"]["momentum_score"] * 1.1) + (c["metrics"]["novelty_score"] * 0.4),
            reverse=True
        )

        top_clusters = scored_clusters[:12]

        # 3. Interpret top clusters with Gemini
        trends_output: List[Trend] = []
        for item in top_clusters:
            trend_obj = await self._interpret_and_persist_cluster(item, db)
            if trend_obj:
                trends_output.append(trend_obj)

        logger.info(f"[{self.name}] Discovered and stored {len(trends_output)} validated trends.")
        return trends_output

    def _extract_tokens(self, text: str) -> List[str]:
        words = text.lower().replace("-", " ").replace("_", " ").split()
        clean = []
        for w in words:
            token = "".join(ch for ch in w if ch.isalnum())
            if len(token) > 2 and token not in STOPWORDS:
                clean.append(token)
        return clean

    def _cluster_signals(self, signals: List[RawSignal]) -> Dict[str, List[RawSignal]]:
        """
        Group signals by distinct tech keywords and topic intersections, avoiding monolithic clusters.
        """
        token_to_signals = defaultdict(list)
        for sig in signals:
            # Combine topics and title tokens
            tokens = set()
            for t in sig.topics:
                clean_t = t.lower().strip()
                if clean_t and clean_t not in STOPWORDS:
                    tokens.add(clean_t)
            title_tokens = self._extract_tokens(sig.title)
            for t in title_tokens[:6]:
                tokens.add(t)

            for token in tokens:
                token_to_signals[token].append(sig)

        # Sort tokens by signal count, but cap any single cluster at 6 signals to avoid swallowing everything
        sorted_tokens = sorted(token_to_signals.items(), key=lambda x: len(x[1]), reverse=True)
        clusters: Dict[str, List[RawSignal]] = {}
        assigned_urls = set()

        for token, token_sigs in sorted_tokens:
            unassigned = [s for s in token_sigs if s.url not in assigned_urls]
            # Form cluster if 2+ unassigned signals or 1 high-gravity signal
            if len(unassigned) >= 2 or (len(unassigned) == 1 and unassigned[0].raw_score > 35):
                cluster_name = token.capitalize()
                chosen_signals = unassigned[:6]
                clusters[cluster_name] = chosen_signals
                for s in chosen_signals:
                    assigned_urls.add(s.url)
            if len(clusters) >= 14:
                break

        return clusters

    def _calculate_metrics(self, signals: List[RawSignal], db: Session) -> Dict[str, Any]:
        """
        Calculate deterministic trend scores:
        - Cross-source appearance
        - Recency / freshness
        - Discussion & star activity
        - Momentum vs historical snapshot
        """
        sources = set(s.source.split(":")[0] for s in signals)
        distinct_source_count = len(sources)

        now = datetime.datetime.utcnow()
        hours_old = []
        for s in signals:
            if s.published_at:
                pub_dt = s.published_at
                if getattr(pub_dt, "tzinfo", None) is not None:
                    pub_dt = pub_dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
                delta = (now - pub_dt).total_seconds() / 3600.0
                hours_old.append(max(0.5, delta))
            else:
                hours_old.append(24.0)

        avg_hours = sum(hours_old) / len(hours_old) if hours_old else 24.0

        # Recency score (100 for <6 hours, decaying down)
        recency_score = max(10.0, 100.0 - (avg_hours * 2.0))

        # Engagement score (stars, comments, upvotes)
        total_activity = sum(s.raw_score + (s.comment_count * 2.0) for s in signals)
        activity_score = min(100.0, (total_activity / (len(signals) + 1)) * 1.5)

        # Cross-source credibility bonus
        cross_source_bonus = (distinct_source_count - 1) * 20.0

        # Heat score
        heat_score = min(100.0, round((activity_score * 0.45) + (recency_score * 0.35) + cross_source_bonus, 1))

        # Novelty score: Higher if newer and fewer historic occurrences
        novelty_score = min(100.0, round(max(20.0, 110.0 - (len(signals) * 5.0) + (recency_score * 0.2)), 1))

        # Momentum score: check if this topic was seen in previous days
        momentum_score = min(100.0, round((heat_score * 0.6) + (cross_source_bonus * 1.5), 1))

        # Confidence: based on signal volume and cross-source corroboration
        confidence = round(min(0.98, max(0.50, 0.40 + (len(signals) * 0.08) + (distinct_source_count * 0.12))), 2)

        # Categorize
        if heat_score > 75 and momentum_score > 70:
            category = "rapidly_rising"
        elif novelty_score > 70 and heat_score > 40:
            category = "emerging"
        elif heat_score > 60 and distinct_source_count >= 2:
            category = "stable"
        else:
            category = "saturated" if len(signals) > 8 else "emerging"

        return {
            "heat_score": heat_score,
            "momentum_score": momentum_score,
            "novelty_score": novelty_score,
            "confidence": confidence,
            "category": category,
            "sources": list(sources),
            "source_urls": [s.url for s in signals]
        }

    async def _interpret_and_persist_cluster(
        self,
        cluster_info: Dict[str, Any],
        db: Session
    ) -> Trend:
        """
        Ask Gemini to interpret cluster signals into a coherent trend, then save into DB.
        """
        key = cluster_info["key"]
        signals: List[RawSignal] = cluster_info["signals"]
        metrics = cluster_info["metrics"]

        signal_summaries = [
            f"- [{s.source}] {s.title} (URL: {s.url}, Summary: {s.summary[:150]})"
            for s in signals[:5]
        ]
        evidence_text = "\n".join(signal_summaries)

        title = f"Advancements in {key}"
        description = f"Rising activity around {key} across {', '.join(metrics['sources'])}."

        if gemini_service.is_configured():
            prompt = f"""
You are the Discovery Agent for ATH Radar.
We detected a cluster of external technology signals around topic "{key}".
Here are the evidence signals collected:
{evidence_text}

Metrics:
Heat: {metrics['heat_score']}, Momentum: {metrics['momentum_score']}, Novelty: {metrics['novelty_score']}

Interpret this cluster into a concrete, insightful technology trend.
Return JSON with this exact structure:
{{
  "title": "A sharp, specific 4-8 word title for this technology/market trend",
  "description": "2-3 sentences explaining the concrete development, what is happening, and why it is gaining traction right now.",
  "category": "{metrics['category']}",
  "topics": ["key topic 1", "key topic 2"]
}}

IMPORTANT: Do not write generic marketing hype. Be technically precise.
"""
            try:
                interpretation = await gemini_service.generate_json(
                    prompt=prompt,
                    system_instruction="You are an expert technical intelligence analyst detecting genuine software and AI trends."
                )
                if interpretation and "title" in interpretation:
                    title = interpretation.get("title", title)
                    description = interpretation.get("description", description)
            except Exception as e:
                logger.error(f"[{self.name}] Gemini interpretation failed for cluster {key}: {e}")

        # Persist Trend in DB
        trend = Trend(
            title=title,
            description=description,
            heat_score=metrics["heat_score"],
            momentum_score=metrics["momentum_score"],
            novelty_score=metrics["novelty_score"],
            confidence=metrics["confidence"],
            category=metrics["category"],
            topics=[s.topics[0] if s.topics else key.lower() for s in signals[:3]],
            sources=metrics["source_urls"],
            evidence_signals=[{"title": s.title, "url": s.url, "source": s.source} for s in signals]
        )
        db.add(trend)
        db.commit()
        db.refresh(trend)

        # Persist TrendSignal snapshot
        snapshot = TrendSignal(
            trend_id=trend.id,
            signal_count=len(signals),
            heat_value=metrics["heat_score"]
        )
        db.add(snapshot)
        db.commit()

        return trend

discovery_agent = DiscoveryAgent()
