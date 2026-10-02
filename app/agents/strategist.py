import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.models import Trend, Connection, ContentIdea, Feedback
from app.services.gemini import gemini_service

from app.services.writing_style import HUMAN_WRITING_SYSTEM_PROMPT, build_human_writing_instruction

logger = logging.getLogger(__name__)

class ContentStrategistAgent:
    """
    Agent 5 — Content Strategist
    Transforms trends + research + personal connections into 15–25 candidate content ideas.
    Avoids generic platitudes; prioritizes experiments, engineering trade-offs, and learnings.
    """
    def __init__(self):
        self.name = "Content Strategist"

    async def run(
        self,
        connections: List[Connection],
        user_profile: Dict[str, Any],
        db: Session
    ) -> List[ContentIdea]:
        logger.info(f"[{self.name}] Generating candidate content ideas across {len(connections)} connections...")

        # Incorporate historical feedback weighting (Section 13)
        past_feedback = db.query(Feedback).order_by(Feedback.created_at.desc()).limit(50).all()
        positive_topics = set()
        negative_topics = set()
        for f in past_feedback:
            if f.action in ("saved", "posted", "useful", "more_like_this"):
                for t in (f.topics or []):
                    positive_topics.add(t.lower())
            elif f.action in ("skipped", "not_useful"):
                for t in (f.topics or []):
                    negative_topics.add(t.lower())

        candidates: List[ContentIdea] = []

        for conn in connections:
            trend = conn.trend
            try:
                ideas_data = await self._generate_ideas_for_connection(
                    conn, trend, user_profile, positive_topics, negative_topics
                )
                for item in ideas_data:
                    idea = ContentIdea(
                        trend_id=trend.id,
                        connection_id=conn.id,
                        title=item.get("title", f"Insight on {trend.title}"),
                        hook=item.get("hook", ""),
                        angle=item.get("angle", ""),
                        explanation=item.get("explanation", ""),
                        why_it_matters=item.get("why_this_is_relevant_to_user", ""),
                        why_user_can_talk_about_it=conn.connection_angle,
                        related_trend=trend.title,
                        personal_connection=item.get("personal_connection", conn.connection_angle),
                        supporting_sources=trend.sources or [],
                        suggested_format=item.get("suggested_format", "breakdown"),
                        novelty=float(item.get("novelty", 0.7)),
                        relevance=float(item.get("relevance", 0.8)),
                        timeliness=float(item.get("timeliness", 0.8)),
                        confidence=float(item.get("confidence", 0.75)),
                        status="candidate",
                        is_editor_approved=False
                    )
                    db.add(idea)
                    candidates.append(idea)
            except Exception as e:
                logger.error(f"[{self.name}] Failed generating ideas for trend '{trend.title}': {e}")

        db.commit()
        for c in candidates:
            db.refresh(c)

        logger.info(f"[{self.name}] Generated {len(candidates)} candidate content ideas.")
        return candidates

    async def _generate_ideas_for_connection(
        self,
        connection: Connection,
        trend: Trend,
        user_profile: Dict[str, Any],
        positive_topics: set,
        negative_topics: set
    ) -> List[Dict[str, Any]]:
        """Generate 2-3 distinct candidate angles per connection."""
        if not gemini_service.is_configured():
            # Deterministic generator with diverse angles and formats
            templates = [
                {
                    "title": f"The Production Autopsy of {trend.title}",
                    "hook": f"Everyone's talking about {trend.title} in theory. Here is the unglamorous memory bottleneck that surfaced under load.",
                    "angle": "Critical debugging & architecture limits",
                    "explanation": f"Examines key claims and trade-offs of {trend.title} from a builder's perspective.",
                    "why_this_is_relevant_to_user": f"Builds on ATH's philosophy of pragmatic systems over hype.",
                    "personal_connection": connection.connection_angle,
                    "suggested_format": "architecture_autopsy",
                    "novelty": 0.88,
                    "relevance": 0.92,
                    "timeliness": 0.85,
                    "confidence": 0.90
                },
                {
                    "title": f"Why Most Teams Overpay for {trend.title}",
                    "hook": f"We ran the math on self-hosting vs hosted API tiers for {trend.title}. The 10x markup is terrifying.",
                    "angle": "Cost & ROI audit vs lean engineering",
                    "explanation": f"Direct breakdown of compute costs, latency penalties, and when simpler heuristics beat heavy architectures.",
                    "why_this_is_relevant_to_user": f"Directly parallels ATH's RouteLLMESH gateway and Pixie local agent efficiency.",
                    "personal_connection": connection.connection_angle,
                    "suggested_format": "cost_roi_audit",
                    "novelty": 0.90,
                    "relevance": 0.88,
                    "timeliness": 0.90,
                    "confidence": 0.88
                },
                {
                    "title": f"The Contrarian Reality Check on {trend.title}",
                    "hook": f"The industry consensus says {trend.title} is mandatory. In practice, 80% of teams would ship faster without it.",
                    "angle": "Unpopular practitioner take grounded in edge cases",
                    "explanation": f"Debunking the hype cycle around {trend.title} by showing real implementation overhead and failure modes.",
                    "why_this_is_relevant_to_user": f"Echoes Ath's decision to avoid bloated agent frameworks in Pixie.",
                    "personal_connection": connection.connection_angle,
                    "suggested_format": "contrarian_reality_check",
                    "novelty": 0.94,
                    "relevance": 0.90,
                    "timeliness": 0.88,
                    "confidence": 0.92
                }
            ]
            return templates

        recent_knowledge = user_profile.get("recent_knowledge_highlights", [])
        recent_text = ""
        if recent_knowledge:
            lines = [f"- [{item.get('type', 'Item').upper()}] {item.get('title')}: {item.get('content', '')[:140]}" for item in recent_knowledge[:6]]
            recent_text = "🔥 ATH'S MOST RECENTLY ADDED KNOWLEDGE (HIGHEST WEIGHTAGE - CONNECT IDEAS HERE FIRST):\n" + "\n".join(lines)

        prompt = f"""
You are the elite Content Strategist for ATH (Ath Tripathi).
Ath wants to build an authentic, magnetic LinkedIn presence as a hands-on AI builder.
He does NOT want repetitive, predictable posts, dry paper summaries, or generic news recaps.
He wants a rich, varied palette of fresh story types: engineering battles, contrarian teardowns, cost breakdowns, tech showdowns, and mental models.

CRITICAL WEIGHTAGE REQUIREMENT:
Give HIGHEST WEIGHTAGE to Ath's MOST RECENTLY ADDED knowledge items and active notes.
Whenever possible, connect the external trend to what Ath just added or explored:

{recent_text}

        # Dynamically build complete registered projects context
        all_projects = user_profile.get("all_projects", [])
        if all_projects:
            proj_lines = []
            for p in all_projects:
                desc = p.get('description', '')
                stack = ', '.join(p.get('tech_stack') or [])
                learnings = p.get('learnings') or p.get('challenges') or ''
                proj_lines.append(f"- {p.get('name')}: {desc} | Stack: {stack} | Learnings/Scars: {learnings}")
            projects_text = "ATH'S REGISTERED PROJECTS (ROTATE FREELY ACROSS ANY OF THESE — NEVER LIMIT TO ONLY 1 OR 2):\n" + "\n".join(proj_lines)
        else:
            projects_text = """ATH'S REGISTERED PROJECTS:
- Bodh AI: Built a real-time Hindi/Hinglish AI voice interviewer. Fought awkward pauses, latency, and conversational flows.
- Pixie: Desktop AI productivity agent built in Rust + Tauri + Python without LangChain/LangGraph.
- RouteLLMESH: Custom self-hosted LLM gateway with heuristic model routing.
- Kundali Dating App: Algorithmic cultural matching combined with AI.
- Vcriate: Technical assessment reviewer (DSA, SQL, edge cases)."""

        all_learning = user_profile.get("all_learning", [])
        learning_text = ""
        if all_learning:
            learn_lines = [f"- {l.get('topic')}: {l.get('description', '')} (Insights: {', '.join(l.get('insights') or [])})" for l in all_learning[:8]]
            learning_text = "ATH'S CURRENT LEARNING TOPICS:\n" + "\n".join(learn_lines)

        prompt = f"""
You are the elite Content Strategist for ATH (Ath Tripathi).
Ath wants to build an authentic, magnetic LinkedIn presence as a hands-on AI builder.
He does NOT want repetitive, predictable posts, dry paper summaries, or generic news recaps.
He wants a rich, varied palette of fresh story types: engineering battles, contrarian teardowns, cost breakdowns, tech showdowns, and mental models.

CRITICAL WEIGHTAGE & DIVERSITY DIRECTIVE:
1. Give HIGHEST WEIGHTAGE to Ath's MOST RECENTLY ADDED knowledge items and active notes.
2. ROTATE ACROSS ALL OF ATH'S PROJECTS & KNOWLEDGE! Do NOT repeatedly ground ideas in only one project. Explore different projects, notes, and learning logs for distinct ideas.
3. Whenever possible, connect the external trend to what Ath just added or explored:

{recent_text}

{projects_text}

{learning_text}

EXTERNAL TREND:
- Title: {trend.title}
- Description: {trend.description}
- Supporting Sources: {trend.sources[:2]}

ATH CONNECTION ANGLE:
{connection.connection_angle} (Related: {connection.related_user_knowledge})

HUMAN WRITING PRINCIPLES TO ENFORCE:
{HUMAN_WRITING_SYSTEM_PROMPT}

AVAILABLE DISTINCT POST FORMATS (Choose 2-3 radically DIFFERENT formats from this menu for contrast):
1. **contrarian_reality_check**: "The Contrarian Reality Check" — Why common hype or industry consensus around this trend breaks down when deployed in real systems.
2. **architecture_autopsy**: "Architecture Autopsy" — A microscopic deep-dive into an unglamorous bug, failure mode, memory leak, or latency bottleneck encountered when building with this.
3. **cost_roi_audit**: "Cost & ROI Audit" — Cold, hard financial & compute numbers comparing hyped hosted APIs vs self-hosted, lightweight alternatives (like RouteLLMESH).
4. **tech_showdown**: "Tech Showdown / Bake-Off" — Direct head-to-head architectural showdown between two competing approaches (e.g. Raw Rust vs bloated frameworks, vLLM vs Ollama, Heuristics vs Agents).
5. **reviewer_diary**: "Code Reviewer Diary" — Connecting this tech shift to common rookie anti-patterns or DSA edge cases observed while reviewing engineering assessments at Vcriate.
6. **builder_war_story**: "Builder War Story" — A gritty first-person battle from shipping Bodh AI or Pixie with concrete metrics and scars ("I spent 3 weeks chasing 400ms latency...").
7. **mental_model**: "Mental Model / First Principles" — An intuitive, visual framework explaining complex low-level mechanics (KV cache, token prefill vs decode, context compression) from scratch.
8. **future_prediction**: "18-Month Frontier Prediction" — A bold, high-signal forecast on where this tech is heading based on hard physical and economic constraints.

CRITICAL RULES:
- Hooks MUST be scroll-stoppers (first 2 lines before "see more" on LinkedIn).
- Commit: make one arguable claim and defend it. Qualify once if genuinely needed, then move on.
- Be specific: replace category nouns with named instances, real numbers, actual dates.
- Vary rhythm: mix short blunt sentences with long ones.
- Cut scaffolding: no scene-setting openers ("In today's fast-paced world"), no "moreover/furthermore/additionally", no "in conclusion".
- Avoid buzzwords (delve, tapestry, landscape, robust, seamless, unlock, elevate, foster, leverage, empower, game-changer), reflexive lists of three, em-dashes as drama beats, "it's not X, it's Y" as punchlines.
- Tone MUST be direct, authentic, builder-first, humble yet technically sharp.
- NEVER fabricate claims. Anchor every story in Ath's real projects.

Return a JSON list of 2-3 objects with DISTINCT suggested_format values:
[
  {{
    "title": "Magnetic headline with builder intrigue",
    "hook": "Unapologetic 1-2 sentence scroll-stopping opening line that makes developers click 'see more'",
    "angle": "Specific narrative angle (e.g. 'Latency war in voice AI', 'Ditching LangChain for raw Rust', 'Why LeetCode fails for agentic systems')",
    "explanation": "The core story arc: The conflict/problem faced -> What Ath did/observed -> The counter-intuitive discovery",
    "why_this_is_relevant_to_user": "How this builds Ath's reputation as a genuine builder who ships real systems",
    "personal_connection": "Specific connection to Bodh AI, Pixie, RouteLLMESH, Vcriate, or current inference learning",
    "suggested_format": "contrarian_reality_check | architecture_autopsy | cost_roi_audit | tech_showdown | reviewer_diary | builder_war_story | mental_model | future_prediction",
    "novelty": 0.92,
    "relevance": 0.95,
    "timeliness": 0.88,
    "confidence": 0.90
  }}
]
"""
        try:
            ideas = await gemini_service.generate_json(
                prompt=prompt,
                system_instruction=build_human_writing_instruction("You are a viral tech storyteller and developer advocate crafting authentic, high-credibility LinkedIn stories.")
            )
            if isinstance(ideas, list) and len(ideas) > 0:
                return ideas
        except Exception as e:
            logger.error(f"[{self.name}] Gemini strategist generation error: {e}")

        return []

content_strategist = ContentStrategistAgent()
