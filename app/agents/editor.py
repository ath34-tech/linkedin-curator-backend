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

        # Previous posts and previous ideas to avoid repetition
        previous_posts = [p.title.lower() for p in db.query(Post).limit(50).all()]
        candidate_ids = {c.id for c in candidates if c.id}
        prev_ideas = db.query(ContentIdea).filter(
            ContentIdea.status.in_(["today", "saved", "posted"])
        ).order_by(ContentIdea.created_at.desc()).limit(150).all()
        previous_idea_titles = [i.title.lower() for i in prev_ideas if i.id not in candidate_ids]

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
            title_lower = idea.title.lower()
            if any(title_lower in prev or prev in title_lower for prev in previous_posts):
                idea.status = "rejected_repetition"
                continue

            # Check for previous idea duplicate overlap
            title_words = set(title_lower.split())
            is_dup = False
            for prev_title in previous_idea_titles:
                prev_words = set(prev_title.split())
                if title_words and prev_words:
                    overlap = len(title_words & prev_words) / len(title_words | prev_words)
                    if overlap >= 0.65 or title_lower == prev_title:
                        is_dup = True
                        break
            if is_dup:
                logger.info(f"[{self.name}] Rejecting idea '{idea.title}' - duplicates previously curated idea.")
                idea.status = "rejected_duplicate_idea"
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

        # 4. Enforce strict Topic, Format, and Project Diversity
        # Prevent monotonous lists of 5 ideas discussing the same topic, using the same template, or citing only 1 project
        final_selection: List[ContentIdea] = []
        selected_trend_ids = set()
        selected_formats = set()
        selected_projects = set()

        all_known_projects = [p.get("name", "").lower() for p in user_profile.get("all_projects", []) if p.get("name")]

        def get_associated_project(idea_obj: ContentIdea) -> str:
            combined = f"{idea_obj.personal_connection or ''} {idea_obj.why_user_can_talk_about_it or ''}".lower()
            for proj in all_known_projects:
                if proj in combined:
                    return proj
            return "general"

        # Pass 1: Unique Trend, Unique Format, and Varied Project
        for idea in scored_ideas:
            if len(final_selection) >= 5:
                break
            trend_key = idea.trend_id or idea.related_trend or idea.title
            fmt_key = idea.suggested_format or "breakdown"
            proj_key = get_associated_project(idea)

            # If project is already selected twice, encourage rotating to other projects
            proj_count = list(selected_projects).count(proj_key) if proj_key != "general" else 0

            if trend_key not in selected_trend_ids and fmt_key not in selected_formats and proj_count < 2:
                final_selection.append(idea)
                selected_trend_ids.add(trend_key)
                selected_formats.add(fmt_key)
                if proj_key != "general":
                    selected_projects.add(proj_key)

        # Pass 2: Unique Trend & Format (relax project constraint)
        if len(final_selection) < 5:
            for idea in scored_ideas:
                if len(final_selection) >= 5:
                    break
                if idea in final_selection:
                    continue
                trend_key = idea.trend_id or idea.related_trend or idea.title
                fmt_key = idea.suggested_format or "breakdown"
                if trend_key not in selected_trend_ids and fmt_key not in selected_formats:
                    final_selection.append(idea)
                    selected_trend_ids.add(trend_key)
                    selected_formats.add(fmt_key)

        # Pass 3: Unique Trend (relax format constraint to ensure 5 distinct trends)
        if len(final_selection) < 5:
            for idea in scored_ideas:
                if len(final_selection) >= 5:
                    break
                if idea in final_selection:
                    continue
                trend_key = idea.trend_id or idea.related_trend or idea.title
                if trend_key not in selected_trend_ids:
                    final_selection.append(idea)
                    selected_trend_ids.add(trend_key)

        # Pass 4: Backfill from remaining top scoring ideas if total trends < 5
        if len(final_selection) < 5:
            for idea in scored_ideas:
                if len(final_selection) >= 5:
                    break
                if idea not in final_selection:
                    final_selection.append(idea)

        for idea in final_selection:
            idea.is_editor_approved = True
            idea.status = "today"

        db.commit()
        for idea in final_selection:
            db.refresh(idea)

        logger.info(f"[{self.name}] Finalized {len(final_selection)} diverse premier content ideas for today's radar.")
        return final_selection

    async def _critique_idea(
        self,
        idea: ContentIdea,
        user_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Criticize and assign final score (0-10) to candidate idea using Human Writing Standards."""
        recent_knowledge = user_profile.get("recent_knowledge_highlights", [])
        recent_titles = [r.get("title", "").lower() for r in recent_knowledge if r.get("title")]

        # Check if this idea connects to recent knowledge
        conn_text = f"{idea.personal_connection or ''} {idea.why_user_can_talk_about_it or ''} {idea.title}".lower()
        has_recent_connection = any(rt in conn_text for rt in recent_titles) if recent_titles else False

        # Baseline deterministic score calculation (+1.5 boost if matching recent knowledge)
        recency_bonus = 1.5 if has_recent_connection else 0.0
        base_score = round(
            min(10.0, (idea.relevance * 3.5) + (idea.novelty * 3.0) + (idea.timeliness * 2.0) + (idea.confidence * 1.5) + recency_bonus),
            1
        )

        if not gemini_service.is_configured():
            return {
                "approved": True,
                "final_score": base_score,
                "confidence": 0.95 if has_recent_connection else 0.85,
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
3. RECENT KNOWLEDGE PRIORITY BOOST: Ath wants heavy weightage on his NEWEST KNOWLEDGE additions. If this idea draws upon his recent experiments or newly added notes, grant it an extra score boost (9.2–9.8)!
4. REJECT BUZZWORDS & SLOP: Reject if it uses words like delve, tapestry, landscape, robust, seamless, unlock, elevate, foster, leverage, empower, game-changer.
5. REJECT CLICHÉ STRUCTURES: Reject reflexive lists of three, drama-beat em-dashes, "it's not X, it's Y" punchlines, or "in today's fast-paced world".
6. REJECT DRY PAPER SUMMARIES: Reject any idea that simply recaps external news without Ath's personal builder scar or counter-intuitive finding.

CANDIDATE IDEA:
- Title: {idea.title}
- Hook: {idea.hook}
- Angle: {idea.angle}
- Story Arc: {idea.explanation}
- Personal Connection: {idea.personal_connection}
- Format: {idea.suggested_format}
- Matches Recent Knowledge: {"YES (HIGH PRIORITY)" if has_recent_connection else "Standard"}

Evaluate and assign a final_score (0-10):
{{
  "approved": true,
  "final_score": {9.5 if has_recent_connection else 9.0},
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
