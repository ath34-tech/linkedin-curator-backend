import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from app.models.database import Base

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), default="ATH")
    bio = Column(Text, nullable=True)
    interests = Column(JSON, default=list)  # list of strings
    skills = Column(JSON, default=list)  # list of strings
    current_learning = Column(JSON, default=list)  # list of strings
    active_projects = Column(JSON, default=list)  # list of strings
    recurring_themes = Column(JSON, default=list)
    topics_understood = Column(JSON, default=list)
    topics_exploring = Column(JSON, default=list)
    content_areas = Column(JSON, default=list)
    tone_guidelines = Column(Text, nullable=True)
    raw_markdown = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    item_type = Column(String(50), default="note")  # note, project, learning, idea, link, document
    topics = Column(JSON, default=list)
    source_url = Column(String(500), nullable=True)
    metadata_json = Column(JSON, default=dict)
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    topics = Column(JSON, default=list)
    image_url = Column(String(500), nullable=True)
    extracted_text = Column(Text, nullable=True)
    is_approved = Column(Boolean, default=True)  # True for direct notes, False for OCR pending review
    status = Column(String(50), default="saved")  # pending_review, saved, archived
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    tech_stack = Column(JSON, default=list)
    status = Column(String(50), default="active")  # active, completed, paused
    learnings = Column(Text, nullable=True)
    challenges = Column(Text, nullable=True)
    link = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class LearningItem(Base):
    __tablename__ = "learning_items"

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    progress_notes = Column(Text, nullable=True)
    key_insights = Column(JSON, default=list)
    resources = Column(JSON, default=list)
    status = Column(String(50), default="learning")  # learning, grasped, parked
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)  # hackernews, github, arxiv, devto, rss
    source_type = Column(String(50), default="api")  # api, rss, scraper
    endpoint = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    last_fetched_at = Column(DateTime, nullable=True)
    items_collected = Column(Integer, default=0)
    config = Column(JSON, default=dict)

class ContentSignal(Base):
    __tablename__ = "content_signals"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    url = Column(String(1000), unique=True, nullable=False, index=True)
    source = Column(String(100), nullable=False, index=True)  # hackernews, github, etc.
    author = Column(String(255), nullable=True)
    published_at = Column(DateTime, default=datetime.datetime.utcnow)
    summary = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    topics = Column(JSON, default=list)
    source_type = Column(String(50), default="api")
    raw_score = Column(Float, default=0.0)
    comment_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Trend(Base):
    __tablename__ = "trends"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False)
    heat_score = Column(Float, default=0.0)
    momentum_score = Column(Float, default=0.0)
    novelty_score = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)
    category = Column(String(50), default="emerging")  # emerging, rapidly_rising, stable, saturated
    topics = Column(JSON, default=list)
    sources = Column(JSON, default=list)  # list of URLs or source names
    evidence_signals = Column(JSON, default=list)  # signal summaries
    research_summary = Column(Text, nullable=True)  # added by Research Agent
    research_details = Column(JSON, default=dict)   # key claims, uncertainties, related tech
    detected_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    signals = relationship("TrendSignal", back_populates="trend", cascade="all, delete-orphan")
    connections = relationship("Connection", back_populates="trend", cascade="all, delete-orphan")

class TrendSignal(Base):
    __tablename__ = "trend_signals"

    id = Column(Integer, primary_key=True, index=True)
    trend_id = Column(Integer, ForeignKey("trends.id"), nullable=False)
    signal_id = Column(Integer, ForeignKey("content_signals.id"), nullable=True)
    snapshot_date = Column(DateTime, default=datetime.datetime.utcnow)
    signal_count = Column(Integer, default=1)
    heat_value = Column(Float, default=0.0)

    trend = relationship("Trend", back_populates="signals")

class Connection(Base):
    __tablename__ = "connections"

    id = Column(Integer, primary_key=True, index=True)
    trend_id = Column(Integer, ForeignKey("trends.id"), nullable=False)
    connection_angle = Column(Text, nullable=False)  # "Why this matters specifically to ATH"
    related_user_knowledge = Column(JSON, default=list)  # items from user profile / learning
    strength_score = Column(Float, default=0.0)
    rationale = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    trend = relationship("Trend", back_populates="connections")
    ideas = relationship("ContentIdea", back_populates="connection")

class ContentIdea(Base):
    __tablename__ = "content_ideas"

    id = Column(Integer, primary_key=True, index=True)
    trend_id = Column(Integer, ForeignKey("trends.id"), nullable=True)
    connection_id = Column(Integer, ForeignKey("connections.id"), nullable=True)
    title = Column(String(500), nullable=False)
    hook = Column(Text, nullable=False)
    angle = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    why_it_matters = Column(Text, nullable=False)
    why_user_can_talk_about_it = Column(Text, nullable=False)
    related_trend = Column(String(255), nullable=True)
    personal_connection = Column(Text, nullable=True)
    supporting_sources = Column(JSON, default=list)
    suggested_format = Column(String(100), default="short_breakdown")  # breakdown, experiment, story, comparison
    novelty = Column(Float, default=0.0)
    relevance = Column(Float, default=0.0)
    timeliness = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)
    final_score = Column(Float, default=0.0)
    status = Column(String(50), default="candidate")  # candidate, today, saved, skipped, posted, archived
    is_editor_approved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    connection = relationship("Connection", back_populates="ideas")
    feedback = relationship("Feedback", back_populates="idea", cascade="all, delete-orphan")
    post = relationship("Post", uselist=False, back_populates="idea")

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    idea_id = Column(Integer, ForeignKey("content_ideas.id"), nullable=True)
    title = Column(String(500), nullable=False)
    final_content = Column(Text, nullable=False)
    platform = Column(String(50), default="linkedin")
    posted_at = Column(DateTime, default=datetime.datetime.utcnow)
    external_url = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)

    idea = relationship("ContentIdea", back_populates="post")

class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    idea_id = Column(Integer, ForeignKey("content_ideas.id"), nullable=False)
    action = Column(String(50), nullable=False)  # saved, skipped, posted, useful, not_useful, more_like_this
    topics = Column(JSON, default=list)
    notes = Column(Text, nullable=True)
    weight = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    idea = relationship("ContentIdea", back_populates="feedback")

class DailyDigest(Base):
    __tablename__ = "daily_digests"

    id = Column(Integer, primary_key=True, index=True)
    digest_date = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    idea_ids = Column(JSON, default=list)
    summary = Column(Text, nullable=True)
    telegram_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
