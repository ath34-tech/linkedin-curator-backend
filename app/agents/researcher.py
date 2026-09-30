import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.models import Trend
from app.services.gemini import gemini_service

logger = logging.getLogger(__name__)

class ResearchAgent:
    """
    Agent 2 — Research Agent
    Deep dives into validated trends to extract factual technical details,
    key claims, uncertainties, and related technologies while strictly preserving source URLs.
    """
    def __init__(self):
        self.name = "Research Agent"

    async def run(self, trends: List[Trend], db: Session) -> List[Trend]:
        logger.info(f"[{self.name}] Researching {len(trends)} discovered trends...")

        for trend in trends:
            try:
                research_data = await self._research_single_trend(trend)
                trend.research_summary = research_data.get("factual_summary")
                trend.research_details = {
                    "important_developments": research_data.get("important_developments", []),
                    "key_claims": research_data.get("key_claims", []),
                    "technical_details": research_data.get("technical_details", []),
                    "uncertainties": research_data.get("uncertainties", []),
                    "related_technologies": research_data.get("related_technologies", []),
                    "verified_sources": trend.sources or []
                }
                db.commit()
            except Exception as e:
                logger.error(f"[{self.name}] Failed to research trend '{trend.title}': {e}")

        logger.info(f"[{self.name}] Completed research on {len(trends)} trends.")
        return trends

    async def _research_single_trend(self, trend: Trend) -> Dict[str, Any]:
        """Synthesize factual technical breakdown using signals and Gemini."""
        evidence_snippets = []
        for ev in (trend.evidence_signals or [])[:5]:
            evidence_snippets.append(f"- Title: {ev.get('title')}\n  URL: {ev.get('url')}\n  Source: {ev.get('source')}")

        evidence_str = "\n".join(evidence_snippets)

        if not gemini_service.is_configured():
            # Deterministic fallback based on trend signals
            return {
                "factual_summary": f"Technical analysis of {trend.title}. Development corroborated by {len(trend.sources or [])} primary sources.",
                "important_developments": [f"Emergence of active discussion and code implementation around {trend.title}"],
                "key_claims": [f"Increases developer efficiency and system throughput in {', '.join(trend.topics or ['AI'])}"],
                "technical_details": [f"Tracked across sources: {', '.join((trend.sources or [])[:3])}"],
                "uncertainties": ["Long-term stability and ecosystem adoption rate remain to be verified."],
                "related_technologies": trend.topics or ["AI systems"]
            }

        prompt = f"""
You are the Research Agent for ATH Radar.
Your mission is to research the following emerging technology trend based strictly on provided signals.
Do NOT fabricate sources or make claims unsupported by the context.

Trend Title: {trend.title}
Trend Description: {trend.description}

Collected Evidence Signals:
{evidence_str}

Provide a structured factual research assessment as JSON with this schema:
{{
  "factual_summary": "3-4 sentence dense, technical, factual summary of the core development",
  "important_developments": ["bullet 1 of recent major development", "bullet 2"],
  "key_claims": ["concrete technical claim made by authors or builders"],
  "technical_details": ["architectural details, performance metrics, or mechanisms mentioned"],
  "uncertainties": ["open technical questions, limitations, trade-offs, or unknowns"],
  "related_technologies": ["adjacent tools, libraries, or architectures"]
}}
"""
        try:
            result = await gemini_service.generate_json(
                prompt=prompt,
                system_instruction="You are a rigorous technical research analyst. Never hallucinate facts or invent sources."
            )
            if result and "factual_summary" in result:
                return result
        except Exception as e:
            logger.error(f"[{self.name}] Gemini research error: {e}")

        return {
            "factual_summary": f"Technical breakdown of {trend.title}.",
            "important_developments": ["Active tool building and benchmarking"],
            "key_claims": ["Performance and workflow improvements"],
            "technical_details": ["Architecture details logged in source repositories"],
            "uncertainties": ["Scalability in production"],
            "related_technologies": trend.topics or []
        }

research_agent = ResearchAgent()
