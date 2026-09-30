from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.models import Source, ContentSignal
from app.schemas.schemas import SourceResponse, ContentSignalResponse

router = APIRouter(prefix="/sources", tags=["Sources"])

@router.get("", response_model=List[SourceResponse])
def get_sources(db: Session = Depends(get_db)):
    sources = db.query(Source).all()
    # If sources table is empty, seed defaults
    if not sources:
        default_sources = [
            Source(name="hackernews", source_type="api", endpoint="https://hn.algolia.com/api/v1/search_by_date", is_active=True),
            Source(name="github", source_type="api", endpoint="https://api.github.com/search/repositories", is_active=True),
            Source(name="arxiv", source_type="api", endpoint="http://export.arxiv.org/api/query", is_active=True),
            Source(name="devto", source_type="api", endpoint="https://dev.to/api/articles", is_active=True),
            Source(name="rss", source_type="rss", endpoint="feedparser_multi_feeds", is_active=True)
        ]
        for s in default_sources:
            db.add(s)
        db.commit()
        sources = db.query(Source).all()
    return sources

@router.get("/signals", response_model=List[ContentSignalResponse])
def get_recent_signals(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(ContentSignal).order_by(ContentSignal.created_at.desc()).limit(limit).all()

@router.post("/{id}/toggle", response_model=SourceResponse)
def toggle_source(id: int, db: Session = Depends(get_db)):
    source = db.query(Source).filter(Source.id == id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    source.is_active = not source.is_active
    db.commit()
    db.refresh(source)
    return source
