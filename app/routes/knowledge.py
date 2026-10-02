from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.models import KnowledgeItem, UserProfile
from app.schemas.schemas import (
    KnowledgeItemCreate, KnowledgeItemUpdate, KnowledgeItemResponse, UserProfileResponse
)

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])

@router.get("", response_model=List[KnowledgeItemResponse])
def get_knowledge(
    item_type: Optional[str] = Query(None, description="Filter by note, project, learning, idea, link, document"),
    search: Optional[str] = Query(None, description="Search keyword in title or content"),
    db: Session = Depends(get_db)
):
    query = db.query(KnowledgeItem).filter(KnowledgeItem.is_archived == False)
    if item_type:
        query = query.filter(KnowledgeItem.item_type == item_type)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            (KnowledgeItem.title.ilike(pattern)) | (KnowledgeItem.content.ilike(pattern))
        )
    return query.order_by(KnowledgeItem.updated_at.desc()).all()

@router.post("", response_model=KnowledgeItemResponse)
def create_knowledge_item(item_in: KnowledgeItemCreate, db: Session = Depends(get_db)):
    item = KnowledgeItem(
        title=item_in.title,
        content=item_in.content,
        item_type=item_in.item_type,
        topics=item_in.topics,
        source_url=item_in.source_url,
        metadata_json=item_in.metadata_json
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

@router.get("/profile", response_model=Optional[UserProfileResponse])
def get_user_profile(db: Session = Depends(get_db)):
    profile = db.query(UserProfile).first()
    return profile

@router.post("/refresh-profile", response_model=Optional[UserProfileResponse])
async def refresh_user_profile(db: Session = Depends(get_db)):
    from app.agents.curator import curator_agent
    await curator_agent.run_async(db)
    return db.query(UserProfile).first()

@router.get("/{id}", response_model=KnowledgeItemResponse)
def get_knowledge_item(id: int, db: Session = Depends(get_db)):
    item = db.query(KnowledgeItem).filter(KnowledgeItem.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    return item

@router.put("/{id}", response_model=KnowledgeItemResponse)
def update_knowledge_item(id: int, item_in: KnowledgeItemUpdate, db: Session = Depends(get_db)):
    item = db.query(KnowledgeItem).filter(KnowledgeItem.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    update_data = item_in.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(item, field, val)

    db.commit()
    db.refresh(item)
    return item

@router.delete("/{id}")
def delete_knowledge_item(id: int, db: Session = Depends(get_db)):
    item = db.query(KnowledgeItem).filter(KnowledgeItem.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    item.is_archived = True
    db.commit()
    return {"status": "success", "message": "Knowledge item archived."}
