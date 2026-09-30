from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.models import Note, KnowledgeItem
from app.schemas.schemas import NoteCreate, NoteUpdate, NoteResponse, OCRReviewResponse, NoteApproveRequest
from app.services.ocr import ocr_service

router = APIRouter(prefix="/notes", tags=["Notes & OCR"])

@router.get("", response_model=List[NoteResponse])
def get_notes(
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Note)
    if status:
        query = query.filter(Note.status == status)
    return query.order_by(Note.created_at.desc()).all()

@router.post("", response_model=NoteResponse)
def create_note(note_in: NoteCreate, db: Session = Depends(get_db)):
    note = Note(
        title=note_in.title,
        content=note_in.content,
        topics=note_in.topics,
        image_url=note_in.image_url,
        extracted_text=note_in.extracted_text,
        is_approved=note_in.is_approved,
        status="saved" if note_in.is_approved else "pending_review",
        metadata_json=note_in.metadata_json
    )
    db.add(note)
    db.commit()
    db.refresh(note)

    # Also register in KnowledgeItem table if approved
    if note.is_approved:
        k_item = KnowledgeItem(
            title=note.title,
            content=note.content,
            item_type="note",
            topics=note.topics,
            metadata_json={"note_id": note.id}
        )
        db.add(k_item)
        db.commit()

    return note

@router.post("/image", response_model=OCRReviewResponse)
async def upload_note_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Image Note Extraction Pipeline:
    Upload -> Gemini Vision OCR -> Extract & Structure Text -> Create Pending Note -> Return for User Review.
    Does NOT finalize until user approves.
    """
    contents = await file.read()
    content_type = file.content_type or "image/jpeg"

    # Process through OCR service
    extracted_data, image_url = await ocr_service.process_note_image(
        image_bytes=contents,
        filename=file.filename or "uploaded_note.jpg",
        content_type=content_type
    )

    # Create unapproved pending note
    pending_note = Note(
        title=extracted_data.get("title", f"Visual Note ({file.filename})"),
        content=extracted_data.get("extracted_text", ""),
        topics=extracted_data.get("topics", []),
        image_url=image_url,
        extracted_text=extracted_data.get("extracted_text", ""),
        is_approved=False,
        status="pending_review",
        metadata_json={
            "summary": extracted_data.get("summary", ""),
            "concepts": extracted_data.get("concepts", []),
            "related_projects": extracted_data.get("related_projects", []),
            "open_questions": extracted_data.get("open_questions", []),
            "filename": file.filename
        }
    )
    db.add(pending_note)
    db.commit()
    db.refresh(pending_note)

    return OCRReviewResponse(
        note_id=pending_note.id,
        title=pending_note.title,
        extracted_text=pending_note.content,
        summary=extracted_data.get("summary", ""),
        topics=pending_note.topics,
        concepts=extracted_data.get("concepts", []),
        related_projects=extracted_data.get("related_projects", []),
        open_questions=extracted_data.get("open_questions", []),
        source=image_url
    )

@router.post("/{id}/approve", response_model=NoteResponse)
def approve_ocr_note(
    id: int,
    approval: NoteApproveRequest,
    db: Session = Depends(get_db)
):
    """
    User reviews and approves extracted content before permanently saving it to knowledge.
    """
    note = db.query(Note).filter(Note.id == id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if approval.title:
        note.title = approval.title
    if approval.content:
        note.content = approval.content
        note.extracted_text = approval.content
    if approval.topics is not None:
        note.topics = approval.topics

    note.is_approved = True
    note.status = "saved"

    # Add to KnowledgeItem searchable store
    k_item = KnowledgeItem(
        title=note.title,
        content=note.content,
        item_type="note",
        topics=note.topics,
        metadata_json={"note_id": note.id, "image_url": note.image_url}
    )
    db.add(k_item)

    db.commit()
    db.refresh(note)
    return note

@router.delete("/{id}")
def delete_note(id: int, db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    db.delete(note)
    db.commit()
    return {"status": "success", "message": "Note deleted."}
