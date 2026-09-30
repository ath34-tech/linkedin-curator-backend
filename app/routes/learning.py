from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.models import LearningItem, KnowledgeItem
from app.schemas.schemas import LearningItemCreate, LearningItemResponse

router = APIRouter(prefix="/learning", tags=["Learning"])

@router.get("", response_model=List[LearningItemResponse])
def get_learning_items(db: Session = Depends(get_db)):
    return db.query(LearningItem).order_by(LearningItem.updated_at.desc()).all()

@router.post("", response_model=LearningItemResponse)
def create_learning_item(learning_in: LearningItemCreate, db: Session = Depends(get_db)):
    item = LearningItem(
        topic=learning_in.topic,
        description=learning_in.description,
        progress_notes=learning_in.progress_notes,
        key_insights=learning_in.key_insights,
        resources=learning_in.resources,
        status=learning_in.status
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    # Ingest into knowledge base
    k_item = KnowledgeItem(
        title=f"Learning: {item.topic}",
        content=f"{item.description or ''}\n\nProgress Notes: {item.progress_notes or ''}\nInsights: {', '.join(item.key_insights)}",
        item_type="learning",
        topics=[item.topic],
        metadata_json={"learning_id": item.id}
    )
    db.add(k_item)
    db.commit()

    return item

@router.delete("/{id}")
def delete_learning_item(id: int, db: Session = Depends(get_db)):
    item = db.query(LearningItem).filter(LearningItem.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Learning item not found")
    db.delete(item)
    db.commit()
    return {"status": "success", "message": "Learning item deleted."}
