import time
import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.models.models import ContentSignal, DailyDigest, ContentIdea
from app.sources import collect_all_sources, deduplicate_signals
from app.agents import (
    curator_agent,
    discovery_agent,
    research_agent,
    connection_agent,
    content_strategist,
    editor_critic
)
from app.services.telegram import telegram_service

logger = logging.getLogger(__name__)

PIPELINE_STATE = {
    "is_running": False,
    "status": "idle",
    "current_step": "idle",
    "last_result": None,
    "last_run_at": None,
    "error": None
}

def get_pipeline_state() -> Dict[str, Any]:
    return dict(PIPELINE_STATE)

async def run_pipeline(send_telegram: bool = True, db: Session = None) -> Dict[str, Any]:
    """
    Deterministic Orchestrator Pipeline for ATH Radar:
    Source collection -> Normalization -> Deduplication ->
    Knowledge Curator -> Discovery Agent -> Research Agent ->
    Connection Agent -> Content Strategist -> Editor/Critic ->
    Save final ideas -> Telegram notification.
    """
    global PIPELINE_STATE

    if PIPELINE_STATE.get("is_running"):
        logger.warning("[Pipeline] Pipeline is already running in background.")
        return {
            "status": "already_running",
            "signals_collected": 0,
            "signals_deduped": 0,
            "trends_found": 0,
            "trends_researched": 0,
            "connections_found": 0,
            "ideas_generated": 0,
            "final_ideas_selected": 0,
            "duration_seconds": 0.0,
            "message": "Pipeline is already actively running in the background."
        }

    start_time = time.time()
    close_db_at_end = False

    if db is None:
        db = SessionLocal()
        close_db_at_end = True

    PIPELINE_STATE["is_running"] = True
    PIPELINE_STATE["status"] = "running"
    PIPELINE_STATE["error"] = None

    try:
        logger.info("==========================================")
        logger.info("🚀 [ATH Radar] Starting Pipeline Execution")
        logger.info("==========================================")

        # 1. Source Collection
        PIPELINE_STATE["current_step"] = "1/8: Sourcing signals from HackerNews, GitHub, Dev.to, ArXiv, and RSS..."
        raw_signals = await collect_all_sources()
        logger.info(f"[Sources] collected {len(raw_signals)} signals")

        # 2. Normalization & Deduplication
        PIPELINE_STATE["current_step"] = "2/8: Normalizing & deduplicating signals..."
        deduped_signals = deduplicate_signals(raw_signals)

        # Store signals in ContentSignal table if not already present
        for sig in deduped_signals:
            exists = db.query(ContentSignal).filter(ContentSignal.url == sig.url).first()
            if not exists:
                db_signal = ContentSignal(
                    title=sig.title,
                    url=sig.url,
                    source=sig.source,
                    author=sig.author,
                    published_at=sig.published_at,
                    summary=sig.summary,
                    content=sig.content,
                    topics=sig.topics,
                    source_type=sig.source_type,
                    raw_score=sig.raw_score,
                    comment_count=sig.comment_count
                )
                db.add(db_signal)
        db.commit()

        # 3. Knowledge Curator (Agent 1)
        PIPELINE_STATE["current_step"] = "3/8: Ingesting your projects, notes, and active learning logs..."
        user_profile = await curator_agent.run_async(db)

        # 4. Discovery Agent (Agent 3)
        PIPELINE_STATE["current_step"] = "4/8: Clustering signals into trend topics..."
        trends = await discovery_agent.run(deduped_signals, db)
        logger.info(f"[Discovery] found {len(trends)} trend clusters")

        if not trends:
            logger.warning("[Pipeline] No trends found. Ending pipeline early.")
            duration = round(time.time() - start_time, 2)
            result = {
                "status": "completed_empty",
                "signals_collected": len(raw_signals),
                "signals_deduped": len(deduped_signals),
                "trends_found": 0,
                "trends_researched": 0,
                "connections_found": 0,
                "ideas_generated": 0,
                "final_ideas_selected": 0,
                "duration_seconds": duration,
                "message": "Pipeline completed: No active trends discovered."
            }
            PIPELINE_STATE["is_running"] = False
            PIPELINE_STATE["status"] = "completed"
            PIPELINE_STATE["current_step"] = "Completed (No trends)"
            PIPELINE_STATE["last_result"] = result
            return result

        # 5. Research Agent (Agent 2)
        PIPELINE_STATE["current_step"] = f"5/8: Deep research & verifying {len(trends)} trends..."
        researched_trends = await research_agent.run(trends, db)
        logger.info(f"[Research] researched {len(researched_trends)} trends")

        # 6. Connection Agent (Agent 4)
        PIPELINE_STATE["current_step"] = "6/8: Finding personal connections to all your projects & notes..."
        connections = await connection_agent.run(researched_trends, user_profile, db)
        logger.info(f"[Connection] found {len(connections)} strong ATH connections")

        # 7. Content Strategist (Agent 5)
        PIPELINE_STATE["current_step"] = "7/8: Generating 8 diverse storytelling formats..."
        candidates = await content_strategist.run(connections, user_profile, db)
        logger.info(f"[Strategist] generated {len(candidates)} ideas")

        # 8. Editor / Critic (Agent 6)
        PIPELINE_STATE["current_step"] = "8/8: Editor scoring & topic/project diversity enforcement..."
        final_ideas = await editor_critic.run(candidates, user_profile, db)
        logger.info(f"[Editor] selected {len(final_ideas)} final ideas")

        # 9. Save Daily Digest Record
        digest = DailyDigest(
            idea_ids=[i.id for i in final_ideas],
            summary=f"Daily Radar generated {len(final_ideas)} ideas from {len(trends)} trends."
        )
        db.add(digest)
        db.commit()

        # 10. Dispatch Telegram Notification if enabled
        if send_telegram and final_ideas and telegram_service.is_configured():
            ideas_payload = [
                {
                    "title": i.title,
                    "hook": i.hook,
                    "angle": i.angle,
                    "personal_connection": i.personal_connection,
                    "suggested_format": i.suggested_format
                }
                for i in final_ideas
            ]
            sent = await telegram_service.send_daily_digest(ideas_payload)
            if sent:
                digest.telegram_sent = True
                db.commit()

        duration = round(time.time() - start_time, 2)
        logger.info(f"✅ [ATH Radar] Pipeline completed successfully in {duration}s")

        result = {
            "status": "success",
            "signals_collected": len(raw_signals),
            "signals_deduped": len(deduped_signals),
            "trends_found": len(trends),
            "trends_researched": len(researched_trends),
            "connections_found": len(connections),
            "ideas_generated": len(candidates),
            "final_ideas_selected": len(final_ideas),
            "duration_seconds": duration,
            "message": f"Successfully generated {len(final_ideas)} curated ideas for today's radar."
        }
        PIPELINE_STATE["is_running"] = False
        PIPELINE_STATE["status"] = "completed"
        PIPELINE_STATE["current_step"] = "Completed"
        PIPELINE_STATE["last_result"] = result
        import datetime
        PIPELINE_STATE["last_run_at"] = datetime.datetime.utcnow().isoformat()
        return result

    except Exception as e:
        logger.error(f"❌ [Pipeline] Execution error: {e}", exc_info=True)
        duration = round(time.time() - start_time, 2)
        result = {
            "status": "error",
            "signals_collected": 0,
            "signals_deduped": 0,
            "trends_found": 0,
            "trends_researched": 0,
            "connections_found": 0,
            "ideas_generated": 0,
            "final_ideas_selected": 0,
            "duration_seconds": duration,
            "message": f"Pipeline failed: {str(e)}"
        }
        PIPELINE_STATE["is_running"] = False
        PIPELINE_STATE["status"] = "failed"
        PIPELINE_STATE["current_step"] = "Failed"
        PIPELINE_STATE["error"] = str(e)
        return result
    finally:
        PIPELINE_STATE["is_running"] = False
        if close_db_at_end and db:
            db.close()
