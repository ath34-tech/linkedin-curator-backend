import logging
import uuid
from pathlib import Path
from typing import Dict, Any, Tuple
from app.services.gemini import gemini_service
from app.config import settings

logger = logging.getLogger(__name__)

UPLOADS_DIR = settings.DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

class OCRService:
    async def process_note_image(
        self,
        image_bytes: bytes,
        filename: str,
        content_type: str
    ) -> Tuple[Dict[str, Any], str]:
        """
        Save the uploaded image locally and invoke Gemini Vision to extract and structure the handwritten/visual note.
        Returns extracted metadata dict and the saved local image path or url.
        """
        # Save file to uploads directory
        ext = Path(filename).suffix or ".jpg"
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        saved_path = UPLOADS_DIR / unique_filename

        with open(saved_path, "wb") as f:
            f.write(image_bytes)

        relative_url = f"/api/uploads/{unique_filename}"

        # If Gemini is configured, run vision extraction
        if gemini_service.is_configured():
            try:
                extraction = await gemini_service.extract_from_image(
                    image_bytes=image_bytes,
                    mime_type=content_type
                )
                if extraction:
                    return extraction, relative_url
            except Exception as e:
                logger.error(f"[OCR] Gemini vision extraction error: {e}")

        # Deterministic fallback if Gemini is offline or rate limited
        fallback = {
            "title": f"Handwritten Note ({filename})",
            "extracted_text": "[Visual note uploaded - awaiting automated text transcription]",
            "summary": "Technical visual diagram / notes uploaded by user.",
            "topics": ["notes", "visual", "technical"],
            "concepts": ["diagram", "architecture"],
            "related_projects": [],
            "open_questions": []
        }
        return fallback, relative_url

ocr_service = OCRService()
