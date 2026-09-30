import json
import logging
import asyncio
import httpx
from typing import Dict, Any, Optional, List
from app.config import settings

logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL or "gemini-3.5-flash-lite"
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 5)

    async def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.4,
        max_output_tokens: int = 4096
    ) -> str:
        """
        Generate text response strictly using the configured Gemini model with 429 backoff.
        """
        if not self.is_configured():
            logger.warning("[Gemini] API key is missing or not configured. Returning empty string.")
            return ""

        url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens
            }
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            async with httpx.AsyncClient(timeout=45.0) as client:
                try:
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts:
                            await asyncio.sleep(1.0)
                            return parts[0].get("text", "")
                    return ""
                except httpx.HTTPStatusError as e:
                    wait_time = 6.0 * attempt if e.response.status_code == 429 else 3.0 * attempt
                    logger.warning(f"[Gemini] Attempt {attempt}/{max_attempts} with '{self.model}' HTTP {e.response.status_code}. Waiting {wait_time}s...")
                    if attempt == max_attempts:
                        raise
                    await asyncio.sleep(wait_time)
                except Exception as e:
                    logger.warning(f"[Gemini] Attempt {attempt}/{max_attempts} with '{self.model}' failed: {e}")
                    if attempt == max_attempts:
                        raise
                    await asyncio.sleep(3.0 * attempt)
        return ""

    async def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2
    ) -> Any:
        """
        Generate structured JSON output strictly using configured Gemini model with 429 backoff.
        """
        if not self.is_configured():
            logger.warning("[Gemini] API key not configured for JSON generation.")
            return None

        url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json"
            }
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            async with httpx.AsyncClient(timeout=60.0) as client:
                try:
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    data = response.json()

                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts:
                            raw_text = parts[0].get("text", "")
                            await asyncio.sleep(1.0)
                            return json.loads(raw_text)
                    return None
                except httpx.HTTPStatusError as e:
                    wait_time = 6.0 * attempt if e.response.status_code == 429 else 3.0 * attempt
                    logger.warning(f"[Gemini] Attempt {attempt}/{max_attempts} for JSON with '{self.model}' HTTP {e.response.status_code}. Waiting {wait_time}s...")
                    if attempt == max_attempts:
                        raise
                    await asyncio.sleep(wait_time)
                except json.JSONDecodeError as jde:
                    logger.error(f"[Gemini] Failed to decode JSON from '{self.model}': {jde}")
                    return None
                except Exception as e:
                    logger.warning(f"[Gemini] Attempt {attempt}/{max_attempts} for JSON with '{self.model}' failed: {e}")
                    if attempt == max_attempts:
                        raise
                    await asyncio.sleep(3.0 * attempt)
        return None

    async def extract_from_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Vision OCR strictly using configured Gemini model.
        """
        import base64
        b64_data = base64.b64encode(image_bytes).decode("utf-8")

        default_prompt = (
            "Analyze this image of handwritten or visual technical notes.\n"
            "Extract all text, diagrams, equations, and structure.\n"
            "Return a clean JSON object with the following schema:\n"
            "{\n"
            '  "title": "A short, descriptive title",\n'
            '  "extracted_text": "Complete verbatim and clean text extracted from the note",\n'
            '  "summary": "2-3 sentence technical summary of what this note is about",\n'
            '  "topics": ["topic1", "topic2", ...],\n'
            '  "concepts": ["core concept 1", "core concept 2", ...],\n'
            '  "related_projects": ["suggested project connections if any"],\n'
            '  "open_questions": ["any unresolved questions or experiments noted"]\n'
            "}"
        )

        final_prompt = prompt or default_prompt
        url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": final_prompt},
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": b64_data
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                if parts:
                    raw_text = parts[0].get("text", "")
                    return json.loads(raw_text)
            return {}

gemini_service = GeminiService()
