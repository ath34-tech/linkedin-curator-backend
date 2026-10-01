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
        """Evaluate intersection between trend and user profile, giving highest weight to recent knowledge."""
        recent_knowledge = user_profile.get("recent_knowledge_highlights", [])
        recent_text = ""
        recent_titles = []
        if recent_knowledge:
            recent_lines = []
            for item in recent_knowledge[:8]:
                t = item.get("title")
                if t:
                    recent_titles.append(t)
                recent_lines.append(f"- [{item.get('type', 'Item').upper()}] {item.get('title')}: {item.get('content', '')[:160]}")
            recent_text = "🔥 ATH'S MOST RECENTLY ADDED KNOWLEDGE & NOTES (HIGHEST WEIGHTAGE - PRIORITIZE FIRST):\n" + "\n".join(recent_lines)

        if not gemini_service.is_configured():
            # Deterministic connection matcher with recency boost
            user_learning = user_profile.get("current_learning", [])
            user_projects = user_profile.get("active_projects", [])
            user_skills = user_profile.get("skills", [])

            # Check overlap with recent knowledge first!
            matched_recent = []
            for r_title in recent_titles:
                for topic in (trend.topics or []):
                    if topic.lower() in r_title.lower() or r_title.lower() in topic.lower():
                        matched_recent.append(r_title)

            matched_items = list(matched_recent)
            for item in user_learning + user_projects + user_skills:
                for topic in (trend.topics or []):
                    if (topic.lower() in item.lower() or item.lower() in topic.lower()) and item not in matched_items:
                        matched_items.append(item)

            if not matched_items:
                matched_items = recent_titles[:1] or user_learning[:1] or ["AI Systems Engineering"]

            is_recent_match = bool(matched_recent)
            strength = 0.95 if is_recent_match else (0.85 if matched_items else 0.6)

            return {
                "connection_angle": f"Connects {trend.title} directly to ATH's {'fresh research into ' + matched_items[0] if is_recent_match else 'work on ' + matched_items[0]}.",
                "related_user_knowledge": matched_items,
                "strength_score": strength,
                "rationale": f"ATH {'recently added notes on ' if is_recent_match else 'actively explores '} {', '.join(matched_items)}, giving immediate grounded authority on this trend."
            }

        prompt = f"""
You are the Connection Agent for ATH Radar.
Your mission is to find the gripping PERSONAL STORY or BUILDER NARRATIVE connecting this external trend to Ath's real work.

CRITICAL WEIGHTAGE DIRECTIVE:
Ath explicitly wants his content radar to give HIGHEST WEIGHTAGE (80% preference) to his MOST RECENTLY ADDED knowledge items and active notes.
Whenever an external trend connects to or challenges his recent notes, learning logs, or projects listed below, PRIORITIZE THAT ANGLE over generic background!

{recent_text}

ATH'S CORE FLAGSHIP PROJECTS (BASELINE GROUNDING):
- Bodh AI: Real-time Hindi/Hinglish AI voice interviewer (LiveKit, WebRTC, Deepgram, Gemini). Battled awkward pauses, end-to-end latency, and robotic conversational flows.
- Pixie: Local-LLM desktop productivity agent in Rust/Tauri/Python. Built custom orchestration without LangChain/LangGraph, fought RAM/latency bottlenecks on small machines.
- RouteLLMESH: Self-hosted LLM gateway with smart heuristic routing to stop burning money on big model APIs.
- Kundali Dating App: Consumer product blending algorithmic cultural matching with modern AI.
- Current Role: Technical assessment reviewer at Vcriate (inspecting DSA & SQL edge cases, constraints, and coding realities).
- Current Learning: Deep-diving into system design, inference engineering (vLLM, KV cache, batching), and preparing an 'Agentic System Design' YouTube breakdown for @TeachMeAth.

EXTERNAL TREND:
- Title: {trend.title}
- Description: {trend.description}
- Research Summary: {trend.research_summary}
- Technical Details: {trend.research_details}

YOUR GOAL:
Find a personal, high-storytelling angle. Connect it to:
- A recent note, learning insight, or struggle Ath just recorded.
- An engineering battle or failure mode (e.g., latency, memory limits, tool schemas).
- A contrarian opinion formed from real experimentation.

Return JSON with this schema:
{{
  "connection_angle": "Punchy 1-2 sentence narrative angle connecting the trend to Ath's newest knowledge additions or actual engineering battles",
  "related_user_knowledge": ["Specific recent note, learning topic, or project name"],
  "strength_score": 0.95,
  "rationale": "Why this gives Ath a distinctive, story-driven perspective that stands out on LinkedIn"
}}
"""
        try:
            res = await gemini_service.generate_json(
                prompt=prompt,
                system_instruction="You are a personal positioning and knowledge strategist. Give top priority to recently added knowledge items. Never invent fake personal experiences."
            )
            if res and "connection_angle" in res:
                return res
        except Exception as e:
            logger.error(f"[{self.name}] Gemini connection error: {e}")

        matched_recent = recent_titles[:1] if recent_titles else user_profile.get('current_learning', ['applied engineering'])
        return {
            "connection_angle": f"Relevant to ATH's recent focus on {matched_recent[0]}",
            "related_user_knowledge": matched_recent,
            "strength_score": 0.85 if recent_titles else 0.7,
            "rationale": "Direct synergy with recently added knowledge and active tech focus."
        }

connection_agent = ConnectionAgent()
