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
            # Deterministic generator
            return [
                {
                    "title": f"The Latency Trade-off in {trend.title}",
                    "hook": f"When benchmarking {trend.title} against raw execution on local hardware, here is the exact failure mode.",
                    "angle": "Practitioner benchmark & cost analysis",
                    "explanation": f"Analyzing {trend.title} through real engineering implementation rather than abstract theory.",
                    "why_this_is_relevant_to_user": f"Directly ties into ATH's active work on {', '.join(user_profile.get('active_projects', ['Radar']))}.",
                    "personal_connection": connection.connection_angle,
                    "suggested_format": "technical_breakdown",
                    "novelty": 0.8,
                    "relevance": 0.85,
                    "timeliness": 0.9,
                    "confidence": 0.8
                },
                {
                    "title": f"The Hidden Constraint in {trend.title}",
                    "hook": f"Before deploying {trend.title}, here is the memory bottleneck that surfaced under load.",
                    "angle": "Critical debugging & architecture limits",
                    "explanation": f"Examines key claims and trade-offs of {trend.title} from a builder's perspective.",
                    "why_this_is_relevant_to_user": f"Builds on ATH's philosophy of pragmatic systems over hype.",
                    "personal_connection": connection.connection_angle,
                    "suggested_format": "lessons_learned",
                    "novelty": 0.75,
                    "relevance": 0.9,
                    "timeliness": 0.8,
                    "confidence": 0.85
                }
            ]

        prompt = f"""
You are the elite Content Strategist for ATH (Ath Tripathi).
Ath wants to build an authentic, magnetic LinkedIn presence as a hands-on AI builder.
He does NOT want to post dry, boring academic paper summaries or generic news.
He wants to tell HIS STORY: engineering battles, struggles, contrarian insights, behind-the-scenes architectural decisions, and honest lessons learned.

ATH'S REAL STORIES & BATTLES:
- Bodh AI: Built a real-time Hindi/Hinglish AI voice interviewer. Fought awkward pauses, end-to-end latency, and robotic dialogue flows. Learned that latency > model IQ for real-time speech.
- Pixie: Desktop AI productivity agent built from scratch in Rust + Tauri + Python. Explicitly rejected LangChain/LangGraph, created custom lightweight tool schema attachments, and fought RAM/context limits on an 8GB machine.
- RouteLLMESH: Built a custom self-hosted LLM gateway with heuristic model routing to stop burning money on OpenAI/Claude API bills.
- Vcriate: Works as a technical assessment reviewer, analyzing hundreds of candidates' DSA & SQL edge cases, constraints, and bugs. Knows the real gap between LeetCode and real AI engineering.
- Kundali Matching Dating App: Consumer product engineering, blending complex cultural astrology matching algorithms with AI.
- Current Learning: Deconstructing system design, vLLM, KV caches, prefill vs decode, and preparing an 'Agentic System Design' breakdown for his YouTube channel (@TeachMeAth).

EXTERNAL TREND:
- Title: {trend.title}
- Description: {trend.description}
- Supporting Sources: {trend.sources[:2]}

ATH CONNECTION ANGLE:
{connection.connection_angle} (Related: {connection.related_user_knowledge})

HUMAN WRITING PRINCIPLES TO ENFORCE:
{HUMAN_WRITING_SYSTEM_PROMPT}

LINKEDIN STORYTELLING FORMATS TO GENERATE (Pick 2-3 distinct angles):
1. **The Builder's Struggle / Post-Mortem**: "I spent 3 weeks trying to solve [X in Bodh AI/Pixie]... here is the counter-intuitive lesson."
2. **The Contrarian Engineering Take**: Why common hype around this trend breaks down when you actually deploy it on real hardware or under real latency constraints.
3. **The Unfiltered Confession / Numbers**: Comparing what popular AI influencers say vs what happens when you write raw Python/Rust without bloated frameworks.
4. **The Code Reviewer's Reality Check**: Connecting this tech shift to real developer habits and common failure modes observed while reviewing assessments.
5. **The First-Principles Learning Journey**: Breaking down a complex mechanism (like KV cache, inference latency, or agent tools) from the perspective of an engineer building and benchmarking it from scratch.

CRITICAL RULES:
- Hooks MUST be scroll-stoppers (first 2 lines before "see more" on LinkedIn).
- Commit: make one arguable claim and defend it. Qualify once if genuinely needed, then move on.
- Be specific: replace category nouns with named instances, real numbers, actual dates.
- Vary rhythm: mix short blunt sentences with long ones.
- Cut scaffolding: no scene-setting openers ("In today's fast-paced world"), no "moreover/furthermore/additionally", no "in conclusion".
- Avoid buzzwords (delve, tapestry, landscape, robust, seamless, unlock, elevate, foster, leverage, empower, game-changer), reflexive lists of three, em-dashes as drama beats, "it's not X, it's Y" as punchlines.
- Tone MUST be direct, authentic, builder-first, humble yet technically sharp.
- NEVER fabricate claims. Anchor every story in Ath's real projects.

Return a JSON list of 2-3 objects:
[
  {{
    "title": "Magnetic headline with builder intrigue",
    "hook": "Unapologetic 1-2 sentence scroll-stopping opening line that makes developers click 'see more'",
    "angle": "Specific narrative angle (e.g. 'Latency war in voice AI', 'Ditching LangChain for raw Rust', 'Why LeetCode fails for agentic systems')",
    "explanation": "The core story arc: The conflict/problem faced -> What Ath did/observed -> The counter-intuitive discovery",
    "why_this_is_relevant_to_user": "How this builds Ath's reputation as a genuine builder who ships real systems",
    "personal_connection": "Specific connection to Bodh AI, Pixie, RouteLLMESH, Vcriate, or current inference learning",
    "suggested_format": "builder_postmortem | contrarian_teardown | behind_the_scenes | learning_in_public",
    "novelty": 0.90,
    "relevance": 0.95,
    "timeliness": 0.85,
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
