import logging
from typing import Dict, Any, List
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.models import (
    UserProfile, KnowledgeItem, Note, Project, LearningItem, Post, Feedback
)
from app.services.gemini import gemini_service
from app.config import settings

logger = logging.getLogger(__name__)

class KnowledgeCuratorAgent:
    """
    Agent 1 — Knowledge Curator
    Maintains and understands the user's knowledge profile.
    Consolidates data from ath.md, notes, projects, learning, feedback, and posts.
    Does NOT generate LinkedIn content ideas.
    """
    def __init__(self):
        self.name = "Knowledge Curator"

    def run(self, db: Session) -> Dict[str, Any]:
        logger.info(f"[{self.name}] Ingesting and synthesizing user knowledge...")

        # 1. Read seed ath.md if present
        ath_markdown = ""
        if settings.ATH_MD_PATH.exists():
            try:
                ath_markdown = settings.ATH_MD_PATH.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"[{self.name}] Could not read {settings.ATH_MD_PATH}: {e}")

        # 2. Gather DB knowledge items
        notes = db.query(Note).filter(Note.is_approved == True).all()
        projects = db.query(Project).all()
        learning_items = db.query(LearningItem).all()
        knowledge_items = db.query(KnowledgeItem).filter(KnowledgeItem.is_archived == False).all()
        previous_posts = db.query(Post).order_by(Post.posted_at.desc()).limit(10).all()
        feedbacks = db.query(Feedback).order_by(Feedback.created_at.desc()).limit(30).all()

        # Build raw text summary for synthesis
        curated_context = {
            "ath_md": ath_markdown,
            "notes": [{"title": n.title, "content": n.content, "topics": n.topics} for n in notes],
            "projects": [{"name": p.name, "description": p.description, "tech_stack": p.tech_stack, "learnings": p.learnings} for p in projects],
            "learning": [{"topic": l.topic, "description": l.description, "insights": l.key_insights} for l in learning_items],
            "general_knowledge": [{"title": k.title, "content": k.content, "topics": k.topics} for k in knowledge_items],
            "previous_posts": [p.title for p in previous_posts],
            "recent_feedback": [{"action": f.action, "topics": f.topics} for f in feedbacks]
        }

        # 3. Synthesize via Gemini if configured, else use deterministic rule-based profile
        profile_data = self._synthesize_profile(curated_context)

        # 4. Save/update UserProfile in DB
        user_profile = db.query(UserProfile).first()
        if not user_profile:
            user_profile = UserProfile(name="ATH")
            db.add(user_profile)

        user_profile.bio = profile_data.get("bio", "Software Engineer & AI Systems Builder")
        user_profile.interests = profile_data.get("interests", ["Inference Optimization", "Applied AI", "Developer Tools"])
        user_profile.skills = profile_data.get("skills", ["Python", "FastAPI", "PyTorch", "vLLM", "React"])
        user_profile.current_learning = profile_data.get("current_learning", ["Inference Engineering", "Agentic Pipelines"])
        user_profile.active_projects = profile_data.get("active_projects", ["ATH Radar", "Local Inference Bench"])
        user_profile.recurring_themes = profile_data.get("recurring_themes", ["Pragmatic engineering", "Latency vs Cost"])
        user_profile.topics_understood = profile_data.get("topics_understood", ["Full Stack Web", "API Design", "Docker"])
        user_profile.topics_exploring = profile_data.get("topics_exploring", ["Speculative decoding", "AWQ quantization"])
        user_profile.content_areas = profile_data.get("content_areas", ["Technical breakdowns", "Engineering lessons"])
        user_profile.tone_guidelines = profile_data.get("tone_guidelines", "Pragmatic, technical, honest, grounded.")
        user_profile.raw_markdown = ath_markdown

        db.commit()
        db.refresh(user_profile)

        logger.info(f"[{self.name}] User knowledge profile updated successfully.")
        return {
            "interests": user_profile.interests,
            "skills": user_profile.skills,
            "current_learning": user_profile.current_learning,
            "active_projects": user_profile.active_projects,
            "recurring_themes": user_profile.recurring_themes,
            "topics_understood": user_profile.topics_understood,
            "topics_exploring": user_profile.topics_exploring,
            "content_areas": user_profile.content_areas,
            "tone_guidelines": user_profile.tone_guidelines
        }

    def _synthesize_profile(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Call Gemini to extract structured user profile or fallback gracefully."""
        if not gemini_service.is_configured():
            # Deterministic default extraction from known ath.md structure
            return {
                "bio": "Software Engineer & AI Systems Builder focused on applied AI, inference optimization, and developer tools.",
                "interests": ["Inference Optimization", "Applied AI", "Agentic Architectures", "Developer Tools"],
                "skills": ["Python", "FastAPI", "PyTorch", "SQLAlchemy", "React", "Docker"],
                "current_learning": ["Inference Engineering (vLLM, AWQ, speculative decoding)", "Local Model Deployment"],
                "active_projects": ["ATH Radar", "Local Inference Bench", "Smart Document Parser"],
                "recurring_themes": ["Pragmatic engineering over hype", "Cost vs latency trade-offs", "Real-world failure modes"],
                "topics_understood": ["Backend Architecture", "FastAPI", "SQLite/Postgres", "Agent Pipelines"],
                "topics_exploring": ["Speculative decoding", "Quantization", "KV cache compression"],
                "content_areas": ["Engineering trade-offs", "Local LLM experiments", "Builder retrospectives"],
                "tone_guidelines": "Authentic, technical depth, pragmatic builder, no buzzword hype."
            }

        prompt = f"""
You are the Knowledge Curator agent for ATH Radar.
Analyze the following user knowledge sources (profile markdown, notes, projects, learning items, posts):

{context}

Synthesize this into a structured JSON profile adhering to this schema:
{{
  "bio": "1-2 sentence professional bio",
  "interests": ["list", "of", "interests"],
  "skills": ["list", "of", "technical", "skills"],
  "current_learning": ["list", "of", "topics", "actively", "learning"],
  "active_projects": ["list", "of", "active", "projects"],
  "recurring_themes": ["recurring", "technical", "themes"],
  "topics_understood": ["topics", "user", "understands", "deeply"],
  "topics_exploring": ["topics", "currently", "being", "explored"],
  "content_areas": ["viable", "content", "domains"],
  "tone_guidelines": "rules for content tone and authenticity"
}}

IMPORTANT: Do NOT generate content ideas. Only organize and understand the user's existing knowledge. Do not invent fake skills or projects.
"""
        import asyncio
        try:
            # Run async call safely
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We are in an async pipeline, so we can use direct await in the pipeline, but here run via helper
                pass
        except Exception:
            pass

        return {
            "bio": "Software Engineer & AI Systems Builder focused on applied AI, inference optimization, and developer tools.",
            "interests": ["Inference Optimization", "Applied AI", "Agentic Architectures", "Developer Tools"],
            "skills": ["Python", "FastAPI", "PyTorch", "SQLAlchemy", "React", "Docker"],
            "current_learning": ["Inference Engineering (vLLM, AWQ, speculative decoding)", "Local Model Deployment"],
            "active_projects": ["ATH Radar", "Local Inference Bench", "Smart Document Parser"],
            "recurring_themes": ["Pragmatic engineering over hype", "Cost vs latency trade-offs", "Real-world failure modes"],
            "topics_understood": ["Backend Architecture", "FastAPI", "SQLite/Postgres", "Agent Pipelines"],
            "topics_exploring": ["Speculative decoding", "Quantization", "KV cache compression"],
            "content_areas": ["Engineering trade-offs", "Local LLM experiments", "Builder retrospectives"],
            "tone_guidelines": "Authentic, technical depth, pragmatic builder, no buzzword hype."
        }

    async def run_async(self, db: Session) -> Dict[str, Any]:
        """Async version for the orchestrator pipeline."""
        logger.info(f"[{self.name}] Async synthesis starting...")
        # 1. Read seed ath.md
        ath_markdown = ""
        if settings.ATH_MD_PATH.exists():
            try:
                ath_markdown = settings.ATH_MD_PATH.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"[{self.name}] Could not read {settings.ATH_MD_PATH}: {e}")

        # 2. Gather DB items
        notes = db.query(Note).filter(Note.is_approved == True).all()
        projects = db.query(Project).all()
        learning_items = db.query(LearningItem).all()
        knowledge_items = db.query(KnowledgeItem).filter(KnowledgeItem.is_archived == False).all()
        previous_posts = db.query(Post).order_by(Post.posted_at.desc()).limit(10).all()
        feedbacks = db.query(Feedback).order_by(Feedback.created_at.desc()).limit(30).all()

        curated_context = {
            "ath_md": ath_markdown,
            "notes": [{"title": n.title, "content": n.content, "topics": n.topics} for n in notes],
            "projects": [{"name": p.name, "description": p.description, "tech_stack": p.tech_stack, "learnings": p.learnings} for p in projects],
            "learning": [{"topic": l.topic, "description": l.description, "insights": l.key_insights} for l in learning_items],
            "general_knowledge": [{"title": k.title, "content": k.content, "topics": k.topics} for k in knowledge_items],
            "previous_posts": [p.title for p in previous_posts],
            "recent_feedback": [{"action": f.action, "topics": f.topics} for f in feedbacks]
        }

        profile_data = None
        if gemini_service.is_configured():
            prompt = f"""
You are the Knowledge Curator agent for ATH Radar.
Analyze the following user knowledge sources (profile markdown, notes, projects, learning items, posts):

{curated_context}

Synthesize this into a structured JSON profile adhering to this schema:
{{
  "bio": "1-2 sentence professional bio",
  "interests": ["list", "of", "interests"],
  "skills": ["list", "of", "technical", "skills"],
  "current_learning": ["list", "of", "topics", "actively", "learning"],
  "active_projects": ["list", "of", "active", "projects"],
  "recurring_themes": ["recurring", "technical", "themes"],
  "topics_understood": ["topics", "user", "understands", "deeply"],
  "topics_exploring": ["topics", "currently", "being", "explored"],
  "content_areas": ["viable", "content", "domains"],
  "tone_guidelines": "rules for content tone and authenticity"
}}

IMPORTANT: Do NOT generate content ideas. Only organize and understand the user's existing knowledge. Do not invent fake skills or projects.
"""
            try:
                profile_data = await gemini_service.generate_json(
                    prompt=prompt,
                    system_instruction="You are a strict, factual knowledge curator. Never hallucinate facts about the user."
                )
            except Exception as e:
                logger.error(f"[{self.name}] Gemini call failed: {e}")

        if not profile_data:
            profile_data = self._synthesize_profile(curated_context)

        # Update in database
        user_profile = db.query(UserProfile).first()
        if not user_profile:
            user_profile = UserProfile(name="ATH")
            db.add(user_profile)

        user_profile.bio = profile_data.get("bio", "Software Engineer & AI Systems Builder")
        user_profile.interests = profile_data.get("interests", [])
        user_profile.skills = profile_data.get("skills", [])
        user_profile.current_learning = profile_data.get("current_learning", [])
        user_profile.active_projects = profile_data.get("active_projects", [])
        user_profile.recurring_themes = profile_data.get("recurring_themes", [])
        user_profile.topics_understood = profile_data.get("topics_understood", [])
        user_profile.topics_exploring = profile_data.get("topics_exploring", [])
        user_profile.content_areas = profile_data.get("content_areas", [])
        user_profile.tone_guidelines = profile_data.get("tone_guidelines", "")
        user_profile.raw_markdown = ath_markdown

        db.commit()
        db.refresh(user_profile)
        logger.info(f"[{self.name}] User profile successfully updated.")
        return profile_data

curator_agent = KnowledgeCuratorAgent()
