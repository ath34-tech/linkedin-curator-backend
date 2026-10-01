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

        # 2. Gather DB knowledge items ordered by recency
        notes = db.query(Note).filter(Note.is_approved == True).order_by(Note.created_at.desc()).all()
        projects = db.query(Project).order_by(Project.created_at.desc()).all()
        learning_items = db.query(LearningItem).order_by(LearningItem.created_at.desc()).all()
        knowledge_items = db.query(KnowledgeItem).filter(KnowledgeItem.is_archived == False).order_by(KnowledgeItem.created_at.desc()).all()
        previous_posts = db.query(Post).order_by(Post.posted_at.desc()).limit(10).all()
        feedbacks = db.query(Feedback).order_by(Feedback.created_at.desc()).limit(30).all()

        # Build highlighted most recent items (highest weightage)
        most_recent_items = []
        for k in knowledge_items[:6]:
            most_recent_items.append({
                "type": f"Knowledge ({k.item_type})",
                "title": k.title,
                "content": k.content,
                "topics": k.topics or [],
                "date": k.created_at.strftime("%Y-%m-%d") if k.created_at else "recent"
            })
        for n in notes[:5]:
            most_recent_items.append({
                "type": "Note",
                "title": n.title,
                "content": n.content or n.extracted_text or "",
                "topics": n.topics or [],
                "date": n.created_at.strftime("%Y-%m-%d") if n.created_at else "recent"
            })
        for l in learning_items[:5]:
            most_recent_items.append({
                "type": "Learning Log",
                "title": l.topic,
                "content": f"{l.description or ''} | Insights: {', '.join(l.key_insights or [])}",
                "topics": [l.topic],
                "date": l.created_at.strftime("%Y-%m-%d") if l.created_at else "recent"
            })
        for p in projects[:5]:
            most_recent_items.append({
                "type": "Project",
                "title": p.name,
                "content": f"{p.description or ''} | Stack: {', '.join(p.tech_stack or [])} | Learnings: {p.learnings or ''}",
                "topics": p.tech_stack or [],
                "date": p.created_at.strftime("%Y-%m-%d") if p.created_at else "recent"
            })

        # Build raw text summary for synthesis with recent items emphasized
        curated_context = {
            "ath_md": ath_markdown,
            "most_recent_knowledge_priority": most_recent_items,
            "notes": [{"title": n.title, "content": n.content, "topics": n.topics} for n in notes],
            "projects": [{"name": p.name, "description": p.description, "tech_stack": p.tech_stack, "learnings": p.learnings} for p in projects],
            "learning": [{"topic": l.topic, "description": l.description, "insights": l.key_insights} for l in learning_items],
            "general_knowledge": [{"title": k.title, "content": k.content, "topics": k.topics} for k in knowledge_items],
            "previous_posts": [p.title for p in previous_posts],
            "recent_feedback": [{"action": f.action, "topics": f.topics} for f in feedbacks]
        }

        # 3. Synthesize via Gemini if configured, else use deterministic rule-based profile
        profile_data = self._synthesize_profile(curated_context)
        profile_data["recent_knowledge_highlights"] = most_recent_items

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
            "tone_guidelines": user_profile.tone_guidelines,
            "recent_knowledge_highlights": most_recent_items
        }

    def _synthesize_profile(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic default extraction or fallback with recent items given top weight."""
        recent_items = context.get("most_recent_knowledge_priority", [])
        recent_topics = []
        for r in recent_items:
            recent_topics.extend(r.get("topics") or [])
            if r.get("title"):
                recent_topics.append(r.get("title"))

        unique_recent = list(dict.fromkeys(recent_topics))[:8]

        return {
            "bio": "Software Engineer & AI Systems Builder focused on applied AI, inference optimization, and developer tools.",
            "interests": unique_recent + ["Inference Optimization", "Applied AI", "Agentic Architectures", "Developer Tools"],
            "skills": ["Python", "FastAPI", "PyTorch", "SQLAlchemy", "React", "Docker"],
            "current_learning": unique_recent[:4] + ["Inference Engineering (vLLM, AWQ, speculative decoding)", "Local Model Deployment"],
            "active_projects": ["ATH Radar", "Local Inference Bench", "Bodh AI", "Pixie"],
            "recurring_themes": ["Pragmatic engineering over hype", "Cost vs latency trade-offs", "Real-world failure modes"],
            "topics_understood": ["Backend Architecture", "FastAPI", "SQLite/Postgres", "Agent Pipelines"],
            "topics_exploring": unique_recent[:5] + ["Speculative decoding", "Quantization", "KV cache compression"],
            "content_areas": ["Engineering trade-offs", "Local LLM experiments", "Builder retrospectives"],
            "tone_guidelines": "Authentic, technical depth, pragmatic builder, no buzzword hype."
        }

    async def run_async(self, db: Session) -> Dict[str, Any]:
        """Async version for the orchestrator pipeline with heavy recency weightage."""
        logger.info(f"[{self.name}] Async synthesis starting with high recency weightage...")
        ath_markdown = ""
        if settings.ATH_MD_PATH.exists():
            try:
                ath_markdown = settings.ATH_MD_PATH.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"[{self.name}] Could not read {settings.ATH_MD_PATH}: {e}")

        # Gather DB items ordered by recency
        notes = db.query(Note).filter(Note.is_approved == True).order_by(Note.created_at.desc()).all()
        projects = db.query(Project).order_by(Project.created_at.desc()).all()
        learning_items = db.query(LearningItem).order_by(LearningItem.created_at.desc()).all()
        knowledge_items = db.query(KnowledgeItem).filter(KnowledgeItem.is_archived == False).order_by(KnowledgeItem.created_at.desc()).all()
        previous_posts = db.query(Post).order_by(Post.posted_at.desc()).limit(10).all()
        feedbacks = db.query(Feedback).order_by(Feedback.created_at.desc()).limit(30).all()

        most_recent_items = []
        for k in knowledge_items[:6]:
            most_recent_items.append({
                "type": f"Knowledge ({k.item_type})",
                "title": k.title,
                "content": k.content,
                "topics": k.topics or [],
                "date": k.created_at.strftime("%Y-%m-%d") if k.created_at else "recent"
            })
        for n in notes[:5]:
            most_recent_items.append({
                "type": "Note",
                "title": n.title,
                "content": n.content or n.extracted_text or "",
                "topics": n.topics or [],
                "date": n.created_at.strftime("%Y-%m-%d") if n.created_at else "recent"
            })
        for l in learning_items[:5]:
            most_recent_items.append({
                "type": "Learning Log",
                "title": l.topic,
                "content": f"{l.description or ''} | Insights: {', '.join(l.key_insights or [])}",
                "topics": [l.topic],
                "date": l.created_at.strftime("%Y-%m-%d") if l.created_at else "recent"
            })
        for p in projects[:5]:
            most_recent_items.append({
                "type": "Project",
                "title": p.name,
                "content": f"{p.description or ''} | Stack: {', '.join(p.tech_stack or [])} | Learnings: {p.learnings or ''}",
                "topics": p.tech_stack or [],
                "date": p.created_at.strftime("%Y-%m-%d") if p.created_at else "recent"
            })

        curated_context = {
            "ath_md": ath_markdown,
            "most_recent_knowledge_priority": most_recent_items,
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
Analyze the following user knowledge sources.

CRITICAL WEIGHTAGE RULE:
Give PARAMOUNT WEIGHTAGE and HIGHEST PRIORITY to the user's MOST RECENTLY ADDED knowledge items, active notes, and newest learning logs in 'most_recent_knowledge_priority'.
Make sure Ath's newest experiments and current learning topics dominate 'current_learning', 'topics_exploring', and 'interests'.

KNOWLEDGE SOURCES:
{curated_context}

Synthesize this into a structured JSON profile adhering to this schema:
{{
  "bio": "1-2 sentence professional bio",
  "interests": ["list", "of", "interests", "prioritizing", "recent"],
  "skills": ["list", "of", "technical", "skills"],
  "current_learning": ["list", "of", "topics", "actively", "learning", "from", "recent", "notes"],
  "active_projects": ["list", "of", "active", "projects"],
  "recurring_themes": ["recurring", "technical", "themes"],
  "topics_understood": ["topics", "user", "understands", "deeply"],
  "topics_exploring": ["topics", "currently", "being", "explored", "heavily", "weighting", "recent"],
  "content_areas": ["viable", "content", "domains"],
  "tone_guidelines": "rules for content tone and authenticity"
}}

IMPORTANT: Do NOT generate content ideas. Only organize and understand the user's existing knowledge. Do not invent fake skills or projects.
"""
            try:
                profile_data = await gemini_service.generate_json(
                    prompt=prompt,
                    system_instruction="You are a strict, factual knowledge curator. Give highest priority to recently added knowledge items."
                )
            except Exception as e:
                logger.error(f"[{self.name}] Gemini call failed: {e}")

        if not profile_data:
            profile_data = self._synthesize_profile(curated_context)

        profile_data["recent_knowledge_highlights"] = most_recent_items

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
        logger.info(f"[{self.name}] User profile successfully updated with recent knowledge weightage.")
        return profile_data

curator_agent = KnowledgeCuratorAgent()
