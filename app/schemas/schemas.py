from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# User Profile
class UserProfileBase(BaseModel):
    name: str = "ATH"
    bio: Optional[str] = None
    interests: List[str] = []
    skills: List[str] = []
    current_learning: List[str] = []
    active_projects: List[str] = []
    recurring_themes: List[str] = []
    topics_understood: List[str] = []
    topics_exploring: List[str] = []
    content_areas: List[str] = []
    tone_guidelines: Optional[str] = None

class UserProfileResponse(UserProfileBase):
    id: int
    raw_markdown: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Knowledge Items
class KnowledgeItemCreate(BaseModel):
    title: str
    content: str
    item_type: str = "note"  # note, project, learning, idea, link, document
    topics: List[str] = []
    source_url: Optional[str] = None
    metadata_json: Dict[str, Any] = {}

class KnowledgeItemUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    item_type: Optional[str] = None
    topics: Optional[List[str]] = None
    source_url: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    is_archived: Optional[bool] = None

class KnowledgeItemResponse(KnowledgeItemCreate):
    id: int
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Notes & OCR Review
class NoteCreate(BaseModel):
    title: str
    content: str
    topics: List[str] = []
    image_url: Optional[str] = None
    extracted_text: Optional[str] = None
    is_approved: bool = True
    metadata_json: Dict[str, Any] = {}

class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    topics: Optional[List[str]] = None
    is_approved: Optional[bool] = None
    status: Optional[str] = None

class NoteApproveRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    topics: Optional[List[str]] = None

class NoteResponse(BaseModel):
    id: int
    title: str
    content: str
    topics: List[str] = []
    image_url: Optional[str] = None
    extracted_text: Optional[str] = None
    is_approved: bool
    status: str
    metadata_json: Dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class OCRReviewResponse(BaseModel):
    note_id: int
    title: str
    extracted_text: str
    summary: str
    topics: List[str] = []
    concepts: List[str] = []
    related_projects: List[str] = []
    open_questions: List[str] = []
    source: str = "image_upload"

# Projects
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    tech_stack: List[str] = []
    status: str = "active"
    learnings: Optional[str] = None
    challenges: Optional[str] = None
    link: Optional[str] = None

class ProjectResponse(ProjectCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Learning Items
class LearningItemCreate(BaseModel):
    topic: str
    description: Optional[str] = None
    progress_notes: Optional[str] = None
    key_insights: List[str] = []
    resources: List[str] = []
    status: str = "learning"

class LearningItemResponse(LearningItemCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Sources & Content Signals
class SourceResponse(BaseModel):
    id: int
    name: str
    source_type: str
    endpoint: Optional[str] = None
    is_active: bool
    last_fetched_at: Optional[datetime] = None
    items_collected: int
    config: Dict[str, Any] = {}

    class Config:
        from_attributes = True

class ContentSignalSchema(BaseModel):
    title: str
    url: str
    source: str
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    topics: List[str] = []
    source_type: str = "api"
    raw_score: float = 0.0
    comment_count: int = 0

class ContentSignalResponse(ContentSignalSchema):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Trends & Connections
class TrendResponse(BaseModel):
    id: int
    title: str
    description: str
    heat_score: float
    momentum_score: float
    novelty_score: float
    confidence: float
    category: str
    topics: List[str] = []
    sources: List[str] = []
    evidence_signals: List[Dict[str, Any]] = []
    research_summary: Optional[str] = None
    research_details: Dict[str, Any] = {}
    detected_at: datetime

    class Config:
        from_attributes = True

class ConnectionResponse(BaseModel):
    id: int
    trend_id: int
    connection_angle: str
    related_user_knowledge: List[str] = []
    strength_score: float
    rationale: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

# Content Ideas & Feedback
class ContentIdeaResponse(BaseModel):
    id: int
    trend_id: Optional[int] = None
    connection_id: Optional[int] = None
    title: str
    hook: str
    angle: str
    explanation: Optional[str] = None
    why_it_matters: str
    why_user_can_talk_about_it: str
    related_trend: Optional[str] = None
    personal_connection: Optional[str] = None
    supporting_sources: List[str] = []
    suggested_format: str
    novelty: float
    relevance: float
    timeliness: float
    confidence: float
    final_score: float
    status: str
    is_editor_approved: bool
    created_at: datetime

    class Config:
        from_attributes = True

class FeedbackCreate(BaseModel):
    action: str  # saved, skipped, posted, useful, not_useful, more_like_this
    notes: Optional[str] = None

class IdeaRewriteRequest(BaseModel):
    instructions: str
    suggested_format: Optional[str] = None

class IdeaDraftRequest(BaseModel):
    custom_instructions: Optional[str] = None
    target_format: Optional[str] = "linkedin"

class IdeaDraftResponse(BaseModel):
    idea_id: int
    headline: str
    draft_content: str

class PostCreate(BaseModel):
    final_content: str
    platform: str = "linkedin"
    external_url: Optional[str] = None
    notes: Optional[str] = None

# App Settings
class AppSettingUpdate(BaseModel):
    key: str
    value: str
    description: Optional[str] = None

class AppSettingResponse(BaseModel):
    key: str
    value: Optional[str] = None
    description: Optional[str] = None
    updated_at: Optional[datetime] = None

class TelegramConfigRequest(BaseModel):
    bot_token: str
    chat_id: str
    daily_digest_time: Optional[str] = "08:30"
    posting_reminder_time: Optional[str] = "17:00"

class TelegramDetectRequest(BaseModel):
    bot_token: Optional[str] = None

class TelegramStatusResponse(BaseModel):
    is_configured: bool
    bot_token_masked: Optional[str] = None
    chat_id: Optional[str] = None
    bot_username: Optional[str] = None
    bot_name: Optional[str] = None
    daily_digest_time: str = "08:30"
    posting_reminder_time: str = "17:00"

# Pipeline Run
class PipelineRunResponse(BaseModel):
    status: str
    signals_collected: int
    signals_deduped: int
    trends_found: int
    trends_researched: int
    connections_found: int
    ideas_generated: int
    final_ideas_selected: int
    duration_seconds: float
    message: str
