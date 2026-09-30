import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.models import Trend, Connection, UserProfile
from app.services.gemini import gemini_service

logger = logging.getLogger(__name__)

class ConnectionAgent:
    """
    Agent 4 — Connection Agent
    Answers: "Why does this matter specifically to ATH?"
    Finds authentic intersections between external trends and ATH's background, active projects, and current learning.
    Does NOT write final posts.
    """
    def __init__(self):
        self.name = "Connection Agent"

    async def run(
        self,
        trends: List[Trend],
        user_profile: Dict[str, Any],
        db: Session
    ) -> List[Connection]:
        logger.info(f"[{self.name}] Finding personal connections for {len(trends)} researched trends...")

        connections: List[Connection] = []
        for trend in trends:
            try:
                conn_data = await self._find_connection(trend, user_profile)
                if conn_data and conn_data.get("strength_score", 0.0) >= 0.5:
                    conn = Connection(
                        trend_id=trend.id,
                        connection_angle=conn_data["connection_angle"],
                        related_user_knowledge=conn_data.get("related_user_knowledge", []),
                        strength_score=float(conn_data.get("strength_score", 0.7)),
                        rationale=conn_data.get("rationale", "")
                    )
                    db.add(conn)
                    connections.append(conn)
            except Exception as e:
                logger.error(f"[{self.name}] Failed to evaluate connection for '{trend.title}': {e}")

        db.commit()
        for c in connections:
            db.refresh(c)

        logger.info(f"[{self.name}] Found {len(connections)} authentic personal connections for ATH.")
        return connections

    async def _find_connection(self, trend: Trend, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate intersection between trend and user profile."""
        if not gemini_service.is_configured():
            # Deterministic connection matcher
            user_learning = user_profile.get("current_learning", [])
            user_projects = user_profile.get("active_projects", [])
            user_skills = user_profile.get("skills", [])

            # Check overlap
            matched_items = []
            for item in user_learning + user_projects + user_skills:
                for topic in (trend.topics or []):
                    if topic.lower() in item.lower() or item.lower() in topic.lower():
                        matched_items.append(item)

            if not matched_items:
                matched_items = user_learning[:1] or ["AI Systems Engineering"]

            return {
                "connection_angle": f"Connects {trend.title} directly to ATH's active exploration of {matched_items[0]}.",
                "related_user_knowledge": matched_items,
                "strength_score": 0.85 if matched_items else 0.6,
                "rationale": f"ATH is actively building and learning around {', '.join(matched_items)}, providing a grounded practitioner lens on this trend."
            }

        prompt = f"""
You are the Connection Agent for ATH Radar.
Your mission is to find the gripping PERSONAL STORY or BUILDER NARRATIVE connecting this external trend to Ath's real work.

ATH'S REAL-WORLD GROUNDING:
- Flagship Projects:
  * Bodh AI: Real-time Hindi/Hinglish AI voice interviewer (LiveKit, WebRTC, Deepgram, Gemini). Battled awkward pauses, end-to-end latency, and robotic conversational flows.
  * Pixie: Local-LLM desktop productivity agent in Rust/Tauri/Python. Built custom orchestration without LangChain/LangGraph, fought RAM/latency bottlenecks on small machines.
  * RouteLLMESH: Self-hosted LLM gateway with smart heuristic routing to stop burning money on big model APIs.
  * Kundali Dating App: Consumer product blending algorithmic cultural matching with modern AI.
  * ReTree & ATLAS: Agent memory and inference-time reasoning exploration.
- Current Role: Technical assessment reviewer at Vcriate (inspecting DSA & SQL edge cases, constraints, and coding realities).
- Current Learning: Deep-diving into system design, inference engineering (vLLM, KV cache, batching), and preparing an 'Agentic System Design' YouTube breakdown for @TeachMeAth.

EXTERNAL TREND:
- Title: {trend.title}
- Description: {trend.description}
- Research Summary: {trend.research_summary}
- Technical Details: {trend.research_details}

YOUR GOAL:
Find a personal, high-storytelling angle. Do NOT treat Ath as a bystander reading a paper. Connect it to:
- A struggle or failure mode Ath faced while building (e.g., latency, memory limits, tool schemas).
- A contrarian opinion formed from real experimentation (e.g., why simple architectures beat hype).
- A direct lesson from reviewing code or learning inference systems from first principles.

Return JSON with this schema:
{{
  "connection_angle": "Punchy 1-2 sentence narrative angle connecting the trend to Ath's actual engineering battles or learning journey",
  "related_user_knowledge": ["Specific project name or learning topic like Bodh AI, Pixie, or Vcriate"],
  "strength_score": 0.90,
  "rationale": "Why this gives Ath a distinctive, story-driven perspective that stands out on LinkedIn"
}}
"""
        try:
            res = await gemini_service.generate_json(
                prompt=prompt,
                system_instruction="You are a personal positioning and knowledge strategist. Never invent fake personal experiences."
            )
            if res and "connection_angle" in res:
                return res
        except Exception as e:
            logger.error(f"[{self.name}] Gemini connection error: {e}")

        return {
            "connection_angle": f"Relevant to ATH's focus on {user_profile.get('current_learning', ['applied engineering'])[0]}",
            "related_user_knowledge": user_profile.get("current_learning", []),
            "strength_score": 0.7,
            "rationale": "High topical synergy with active tech stack."
        }

connection_agent = ConnectionAgent()
