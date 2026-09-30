import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.models import ContentIdea, Post
from app.services.gemini import gemini_service

from app.services.writing_style import (
    HUMAN_WRITING_SYSTEM_PROMPT,
    build_human_writing_instruction,
    check_human_writing_violations,
    FORBIDDEN_BUZZWORDS,
    FORBIDDEN_SCAFFOLDING
)

logger = logging.getLogger(__name__)

class EditorCriticAgent:
    """
    Agent 6 — Editor/Critic
    Rigorously filters candidate content ideas to select the final 5–10 highest-quality,
    authentic ideas. Rejects generic fluff, fake claims, buzzwords, and AI slop.
    """
    def __init__(self):
        self.name = "Editor/Critic"

    async def run(
        self,
        candidates: List[ContentIdea],
        user_profile: Dict[str, Any],
        db: Session
    ) -> List[ContentIdea]:
        logger.info(f"[{self.name}] Reviewing {len(candidates)} candidate ideas against Human Writing Standards...")

        if not candidates:
            return []

        # Previous posts to avoid repetition
        previous_posts = [p.title.lower() for p in db.query(Post).limit(20).all()]

        # 1. Deterministic filter pass (buzzwords, scaffolding, repetition)
        valid_candidates: List[ContentIdea] = []
        for idea in candidates:
            text_to_check = f"{idea.title} {idea.hook} {idea.explanation or ''}"
            violations = check_human_writing_violations(text_to_check)
            if violations:
                logger.info(f"[{self.name}] Rejecting idea '{idea.title}' due to violations: {violations}")
                idea.status = "rejected_ai_buzzwords"
                continue

            # Check for previous post overlap
            if any(idea.title.lower() in prev or prev in idea.title.lower() for prev in previous_posts):
                idea.status = "rejected_repetition"
                continue

            valid_candidates.append(idea)

        logger.info(f"[{self.name}] {len(valid_candidates)} candidates passed deterministic screening.")

        # 2. Strict AI / algorithmic scoring
        scored_ideas = []
        for idea in valid_candidates:
            evaluation = await self._critique_idea(idea, user_profile)
            if evaluation.get("approved", True):
                idea.final_score = float(evaluation.get("final_score", 8.0))
                idea.confidence = float(evaluation.get("confidence", idea.confidence))
                idea.why_it_matters = evaluation.get("why_it_matters", idea.why_it_matters)
                idea.why_user_can_talk_about_it = evaluation.get("why_user_can_talk_about_it", idea.why_user_can_talk_about_it)
                idea.suggested_format = evaluation.get("suggested_format", idea.suggested_format)
                scored_ideas.append(idea)
            else:
                idea.status = f"rejected_{evaluation.get('rejection_reason', 'critic')}"

        # 3. Sort by final score descending
        scored_ideas.sort(key=lambda i: i.final_score, reverse=True)

        # 4. Select top 5-10
        final_selection = scored_ideas[:10]
        if len(final_selection) < 5 and scored_ideas:
            final_selection = scored_ideas[:min(5, len(scored_ideas))]

        for idea in final_selection:
            idea.is_editor_approved = True
            idea.status = "today"

        db.commit()
        for idea in final_selection:
            db.refresh(idea)

        logger.info(f"[{self.name}] Finalized {len(final_selection)} premier content ideas for today's radar.")
        return final_selection

    async def _critique_idea(
        self,
        idea: ContentIdea,
        user_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Criticize and assign final score (0-10) to candidate idea using Human Writing Standards."""
        # Baseline deterministic score calculation
        base_score = round(
            (idea.relevance * 3.5) + (idea.novelty * 3.0) + (idea.timeliness * 2.0) + (idea.confidence * 1.5),
            1
        )

        if not gemini_service.is_configured():
            return {
                "approved": True,
                "final_score": base_score,
                "confidence": 0.85,
                "why_it_matters": idea.why_it_matters or "Direct technical relevance to current developer trends.",
                "why_user_can_talk_about_it": idea.why_user_can_talk_about_it or idea.personal_connection,
                "suggested_format": idea.suggested_format
            }

        prompt = f"""
You are the Editor/Critic Agent for ATH Radar.
Ath wants to build an authentic, magnetic LinkedIn presence as an AI builder who tells real stories from the trenches (not dry paper recaps).

HUMAN WRITING PRINCIPLES CHECKLIST:
1. SPECIFIC REAL POSITION: Does this make one clear, arguable claim rather than a generic survey?
2. PERSONAL BUILDER SCARS: Is the idea anchored in Ath's real experience (Bodh AI voice latency, Pixie 8GB RAM constraints, RouteLLMESH routing, Vcriate code review insights)?
3. REJECT BUZZWORDS & SLOP: Reject if it uses words like delve, tapestry, landscape, robust, seamless, unlock, elevate, foster, leverage, empower, game-changer.
4. REJECT CLICHÉ STRUCTURES: Reject reflexive lists of three, drama-beat em-dashes, "it's not X, it's Y" punchlines, or "in today's fast-paced world".
5. REJECT DRY PAPER SUMMARIES: Reject any idea that simply recaps external news without Ath's personal builder scar or counter-intuitive finding.

CANDIDATE IDEA:
- Title: {idea.title}
- Hook: {idea.hook}
- Angle: {idea.angle}
- Story Arc: {idea.explanation}
- Personal Connection: {idea.personal_connection}
- Format: {idea.suggested_format}

Evaluate and assign a final_score (0-10):
{{
  "approved": true,
  "final_score": 9.2,
  "confidence": 0.95,
  "why_it_matters": "Why this narrative will generate high engagement and genuine developer respect on LinkedIn",
  "why_user_can_talk_about_it": "Why Ath's real projects give him the authentic authority to tell this story",
  "suggested_format": "{idea.suggested_format}",
  "rejection_reason": "none or reason if approved is false"
}}
"""
        try:
            res = await gemini_service.generate_json(
                prompt=prompt,
                system_instruction=build_human_writing_instruction("You are an uncompromising LinkedIn content director who turns real engineering battles into viral, high-credibility developer stories.")
            )
            if res and "approved" in res:
                return res
        except Exception as e:
            logger.error(f"[{self.name}] Gemini critique error: {e}")

        return {
            "approved": True,
            "final_score": base_score,
            "confidence": 0.8,
            "why_it_matters": idea.why_it_matters,
            "why_user_can_talk_about_it": idea.why_user_can_talk_about_it,
            "suggested_format": idea.suggested_format
        }

editor_critic = EditorCriticAgent()
