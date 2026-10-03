import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.models import ContentIdea, Feedback, Post
from app.schemas.schemas import (
    ContentIdeaResponse, FeedbackCreate, PostCreate, PipelineRunResponse,
    PipelineStatusResponse, IdeaRewriteRequest, IdeaDraftRequest, IdeaDraftResponse
)
from app.orchestrator.pipeline import run_pipeline, get_pipeline_state
from app.services.gemini import gemini_service
from app.services.writing_style import (
    HUMAN_WRITING_SYSTEM_PROMPT,
    build_human_writing_instruction,
    check_human_writing_violations
)

router = APIRouter(prefix="/ideas", tags=["Ideas"])

@router.get("", response_model=List[ContentIdeaResponse])
def get_all_ideas(
    status: Optional[str] = Query(None, description="Filter by status: today, saved, skipped, posted, candidate"),
    db: Session = Depends(get_db)
):
    query = db.query(ContentIdea)
    if status:
        query = query.filter(ContentIdea.status == status)
    return query.order_by(ContentIdea.final_score.desc(), ContentIdea.created_at.desc()).all()

@router.get("/today", response_model=List[ContentIdeaResponse])
def get_today_ideas(db: Session = Depends(get_db)):
    # Return ideas marked as "today" or candidate created within last 24h
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    ideas = db.query(ContentIdea).filter(
        ContentIdea.status.in_(["today", "candidate"]),
        ContentIdea.is_editor_approved == True,
        ContentIdea.created_at >= cutoff
    ).order_by(ContentIdea.final_score.desc()).limit(10).all()

    # Fallback to recent approved ideas if today's count is low (NEVER return saved, posted, or skipped items)
    if len(ideas) < 5:
        fallback = db.query(ContentIdea).filter(
            ContentIdea.is_editor_approved == True,
            ContentIdea.status.in_(["today", "candidate"])
        ).order_by(ContentIdea.final_score.desc(), ContentIdea.created_at.desc()).limit(10).all()
        return fallback

    return ideas

@router.post("/{id}/save", response_model=ContentIdeaResponse)
def save_idea(id: int, db: Session = Depends(get_db)):
    idea = db.query(ContentIdea).filter(ContentIdea.id == id).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    
    idea.status = "saved"
    db.add(Feedback(idea_id=idea.id, action="saved", topics=idea.connection.related_user_knowledge if idea.connection else []))
    db.commit()
    db.refresh(idea)
    return idea

@router.post("/{id}/skip", response_model=ContentIdeaResponse)
def skip_idea(id: int, db: Session = Depends(get_db)):
    idea = db.query(ContentIdea).filter(ContentIdea.id == id).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    
    idea.status = "skipped"
    db.add(Feedback(idea_id=idea.id, action="skipped", topics=idea.connection.related_user_knowledge if idea.connection else []))
    db.commit()
    db.refresh(idea)
    return idea

@router.post("/{id}/posted")
def mark_posted(id: int, post_data: Optional[PostCreate] = None, db: Session = Depends(get_db)):
    idea = db.query(ContentIdea).filter(ContentIdea.id == id).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    idea.status = "posted"

    content = post_data.final_content if post_data else idea.title + "\n\n" + (idea.explanation or idea.hook)
    platform = post_data.platform if post_data else "linkedin"
    external_url = post_data.external_url if post_data else None
    notes = post_data.notes if post_data else None

    post = Post(
        idea_id=idea.id,
        title=idea.title,
        final_content=content,
        platform=platform,
        external_url=external_url,
        notes=notes
    )
    db.add(post)
    db.add(Feedback(idea_id=idea.id, action="posted", topics=idea.connection.related_user_knowledge if idea.connection else []))
    db.commit()
    db.refresh(idea)
    return {"status": "success", "idea_id": idea.id, "post_id": post.id}

@router.post("/{id}/feedback")
def submit_feedback(id: int, feedback_in: FeedbackCreate, db: Session = Depends(get_db)):
    idea = db.query(ContentIdea).filter(ContentIdea.id == id).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    fb = Feedback(
        idea_id=idea.id,
        action=feedback_in.action,
        notes=feedback_in.notes,
        topics=idea.connection.related_user_knowledge if idea.connection else []
    )
    db.add(fb)
    db.commit()
    return {"status": "success", "message": f"Feedback '{feedback_in.action}' recorded."}

@router.post("/{id}/rewrite", response_model=ContentIdeaResponse)
async def rewrite_idea(
    id: int,
    req: IdeaRewriteRequest,
    db: Session = Depends(get_db)
):
    """
    Request an AI rewrite of an existing idea with custom user steering and guidance.
    """
    idea = db.query(ContentIdea).filter(ContentIdea.id == id).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    prompt = f"""
You are the elite Content Strategist for ATH (Ath Tripathi).
The user likes the topic of this content idea, but wants it REWRITTEN according to their specific guidance.

CURRENT IDEA:
- Title: {idea.title}
- Hook: {idea.hook}
- Angle: {idea.angle}
- Story/Explanation: {idea.explanation}
- Related Topic/Trend: {idea.related_trend}
- Personal Connection: {idea.personal_connection}

USER REWRITE INSTRUCTIONS:
"{req.instructions}"

{f"Target Format: {req.suggested_format}" if req.suggested_format else ""}

ATH'S REAL BUILDER CONTEXT:
- Bodh AI: Real-time Hindi/Hinglish AI voice interviewer. Fought awkward pauses, speech latency, and conversational flow.
- Pixie: Local-LLM desktop productivity agent in Rust + Tauri + Python. Fought RAM/latency on 8GB machine without LangChain.
- RouteLLMESH: Self-hosted LLM gateway with smart heuristic routing to cut API bills.
- Vcriate: Technical assessment reviewer checking DSA & SQL edge cases.
- Kundali Matching Dating App: Consumer product engineering with cultural matching algorithms.
- Current Learning: System design, vLLM, KV cache, prefill vs decode, TeachMeAth YouTube.

HUMAN WRITING PRINCIPLES (MANDATORY):
{HUMAN_WRITING_SYSTEM_PROMPT}

Rewrite this idea into a high-engagement, viral, scroll-stopping LinkedIn story strictly following the user's instructions and the Human Writing Principles.
Return a JSON object with this exact schema:
{{
  "title": "Sharper, compelling headline",
  "hook": "Unapologetic 1-2 sentence scroll-stopping opening line",
  "angle": "Updated narrative angle reflecting the user's feedback",
  "explanation": "Rewritten story arc and core insight addressing the user's instructions",
  "why_it_matters": "Why this narrative hits hard and provides value",
  "personal_connection": "Concrete connection to Ath's projects",
  "suggested_format": "{req.suggested_format or idea.suggested_format}"
}}
"""
    try:
        rewritten = await gemini_service.generate_json(
            prompt=prompt,
            system_instruction=build_human_writing_instruction("You are a premier developer advocate and viral tech storyteller rewriting ideas based on specific creator direction.")
        )
        if rewritten and "title" in rewritten:
            idea.title = rewritten.get("title", idea.title)
            idea.hook = rewritten.get("hook", idea.hook)
            idea.angle = rewritten.get("angle", idea.angle)
            idea.explanation = rewritten.get("explanation", idea.explanation)
            idea.why_it_matters = rewritten.get("why_it_matters", idea.why_it_matters)
            idea.personal_connection = rewritten.get("personal_connection", idea.personal_connection)
            if req.suggested_format:
                idea.suggested_format = req.suggested_format
            elif rewritten.get("suggested_format"):
                idea.suggested_format = rewritten["suggested_format"]

            db.commit()
            db.refresh(idea)
            return idea
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rewrite failed: {str(e)}")

    return idea

@router.post("/{id}/draft", response_model=IdeaDraftResponse)
async def generate_post_draft(
    id: int,
    req: Optional[IdeaDraftRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Generate a full, ready-to-publish LinkedIn post from an idea, strictly
    following the Human Writing Principles (one arguable claim, named instances,
    varied rhythm, zero scaffolding, zero buzzwords).
    """
    idea = db.query(ContentIdea).filter(ContentIdea.id == id).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    custom_notes = req.custom_instructions if req and req.custom_instructions else ""

    prompt = f"""
Draft a complete, authentic LinkedIn post based on this approved content idea for ATH (Ath Tripathi).

IDEA DETAILS:
- Title: {idea.title}
- Hook: {idea.hook}
- Narrative Angle: {idea.angle}
- Story/Insight: {idea.explanation}
- Builder Connection: {idea.personal_connection}
- Why It Matters: {idea.why_it_matters}
{f"- User Guidance: {custom_notes}" if custom_notes else ""}

ATH'S CONTEXT:
Ath is a hands-on engineer building Bodh AI (Hindi voice AI), Pixie (Rust/Tauri local agent on 8GB RAM without LangChain), RouteLLMESH (LLM gateway), and reviewing technical assessments at Vcriate.

HUMAN WRITING INSTRUCTIONS:
{HUMAN_WRITING_SYSTEM_PROMPT}

ADDITIONAL CONSTRAINTS FOR THE DRAFT:
1. Start directly on the opening hook line. Do NOT say 'Here is your draft:' or add meta commentary.
2. Vary sentence lengths drastically. Short punches. Then an expansive engineering thought.
3. Replace generic claims with specific numbers, latencies, or architectural decisions.
4. Stop when the last point is made. Do NOT add cheesy questions ('What do you think? Drop a comment below!'), do NOT add lists of 10 hashtags. At most 2-3 focused hashtags.
5. NO buzzwords (delve, tapestry, landscape, robust, seamless, unlock, elevate, foster, leverage, empower, game-changer).
6. NO em-dashes as drama beats ('—').
7. NO 'it's not X, it's Y' punchlines.

Output ONLY the final post text.
"""
    try:
        draft_text = await gemini_service.generate_text(
            prompt=prompt,
            system_instruction=build_human_writing_instruction("You are Ath Tripathi drafting a direct, high-credibility personal LinkedIn post from the trenches.")
        )
        if draft_text:
            return IdeaDraftResponse(
                idea_id=idea.id,
                headline=idea.title,
                draft_content=draft_text.strip()
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Draft generation failed: {str(e)}")

    # Fallback draft if Gemini unavailable
    fallback_content = f"{idea.hook}\n\n{idea.explanation}\n\nKey lesson from {idea.personal_connection or 'building'}:\nArchitecture trade-offs always show up under production load."
    return IdeaDraftResponse(
        idea_id=idea.id,
        headline=idea.title,
        draft_content=fallback_content
    )

@router.get("/pipeline-status", response_model=PipelineStatusResponse)
def get_pipeline_status():
    """Check current status and step of the radar pipeline."""
    return get_pipeline_state()

@router.post("/run-pipeline", response_model=PipelineRunResponse)
async def trigger_pipeline_run(background_tasks: BackgroundTasks):
    """
    Trigger execution of the 6-agent radar pipeline in the background.
    Responds immediately (preventing HTTP timeouts / connection drops on Render).
    """
    state = get_pipeline_state()
    if state.get("is_running"):
        return PipelineRunResponse(
            status="running",
            message="Radar pipeline is already actively running in the background. Fresh ideas will appear shortly."
        )

    # Launch background task
    background_tasks.add_task(run_pipeline, send_telegram=True)

    return PipelineRunResponse(
        status="started",
        message="Radar pipeline launched in the background. Sourcing feeds and synthesizing ideas..."
    )

