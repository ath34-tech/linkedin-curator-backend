import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db, SessionLocal
from app.models.models import AppSetting, ContentIdea
from app.schemas.schemas import (
    AppSettingUpdate, AppSettingResponse,
    TelegramConfigRequest, TelegramDetectRequest, TelegramStatusResponse
)
from app.config import settings
from app.services.telegram import telegram_service
from app.services.gemini import gemini_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Settings"])

DEFAULT_SETTINGS = {
    "GEMINI_API_KEY": settings.GEMINI_API_KEY,
    "GEMINI_MODEL": settings.GEMINI_MODEL,
    "TELEGRAM_BOT_TOKEN": settings.TELEGRAM_BOT_TOKEN,
    "TELEGRAM_CHAT_ID": settings.TELEGRAM_CHAT_ID,
    "DAILY_DIGEST_TIME": settings.DAILY_DIGEST_TIME,
    "POSTING_REMINDER_TIME": settings.POSTING_REMINDER_TIME,
    "ENABLE_SCHEDULER": str(settings.ENABLE_SCHEDULER).lower(),
}

def sync_settings_from_db(db: Optional[Session] = None):
    """Sync persistent DB settings into running service instances."""
    close_at_end = False
    if db is None:
        db = SessionLocal()
        close_at_end = True

    try:
        db_settings = {s.key: s.value for s in db.query(AppSetting).all()}

        if "GEMINI_API_KEY" in db_settings and db_settings["GEMINI_API_KEY"]:
            gemini_service.api_key = db_settings["GEMINI_API_KEY"]
        if "GEMINI_MODEL" in db_settings and db_settings["GEMINI_MODEL"]:
            gemini_service.model = db_settings["GEMINI_MODEL"]
        if "TELEGRAM_BOT_TOKEN" in db_settings and db_settings["TELEGRAM_BOT_TOKEN"]:
            telegram_service.bot_token = db_settings["TELEGRAM_BOT_TOKEN"]
        if "TELEGRAM_CHAT_ID" in db_settings and db_settings["TELEGRAM_CHAT_ID"]:
            telegram_service.chat_id = db_settings["TELEGRAM_CHAT_ID"]

        logger.info("[Settings] In-memory services synced from database.")
    finally:
        if close_at_end:
            db.close()

def _mask_value(key: str, val: Optional[str]) -> Optional[str]:
    if not val:
        return val
    if "KEY" in key or "TOKEN" in key:
        if len(val) > 8:
            return val[:4] + "..." + val[-4:]
    return val

@router.get("", response_model=List[AppSettingResponse])
def get_settings(db: Session = Depends(get_db)):
    db_settings = {s.key: s for s in db.query(AppSetting).all()}
    results = []

    for key, val in DEFAULT_SETTINGS.items():
        if key in db_settings:
            item = db_settings[key]
            masked_val = _mask_value(key, item.value)
            results.append(AppSettingResponse(key=key, value=masked_val, description=item.description, updated_at=item.updated_at))
        else:
            masked_val = _mask_value(key, val)
            results.append(AppSettingResponse(key=key, value=masked_val, description=f"Configuration for {key}"))

    return results

@router.put("", response_model=AppSettingResponse)
def update_setting(payload: AppSettingUpdate, db: Session = Depends(get_db)):
    setting = db.query(AppSetting).filter(AppSetting.key == payload.key).first()
    if not setting:
        setting = AppSetting(key=payload.key, value=payload.value, description=payload.description)
        db.add(setting)
    else:
        setting.value = payload.value
        if payload.description:
            setting.description = payload.description

    db.commit()
    db.refresh(setting)

    # Sync dynamically
    sync_settings_from_db(db)

    return setting

# --- Dedicated Telegram Settings Endpoints ---

@router.get("/telegram", response_model=TelegramStatusResponse)
async def get_telegram_status(db: Session = Depends(get_db)):
    """Fetch structured status of Telegram integration with live bot validation."""
    sync_settings_from_db(db)

    token = telegram_service.bot_token or ""
    chat_id = telegram_service.chat_id or ""

    # Read schedules from DB or defaults
    digest_setting = db.query(AppSetting).filter(AppSetting.key == "DAILY_DIGEST_TIME").first()
    reminder_setting = db.query(AppSetting).filter(AppSetting.key == "POSTING_REMINDER_TIME").first()

    digest_time = digest_setting.value if digest_setting else settings.DAILY_DIGEST_TIME
    reminder_time = reminder_setting.value if reminder_setting else settings.POSTING_REMINDER_TIME

    bot_username = None
    bot_name = None

    if token and len(token) > 10:
        bot_check = await telegram_service.verify_bot_token(token)
        if bot_check.get("valid"):
            bot_username = bot_check.get("bot_username")
            bot_name = bot_check.get("bot_name")

    return TelegramStatusResponse(
        is_configured=telegram_service.is_configured(),
        bot_token_masked=_mask_value("TOKEN", token),
        chat_id=chat_id,
        bot_username=bot_username,
        bot_name=bot_name,
        daily_digest_time=digest_time,
        posting_reminder_time=reminder_time
    )

@router.post("/telegram/verify-token")
async def verify_telegram_token(payload: TelegramDetectRequest):
    """Verify if a Telegram Bot token is valid before saving."""
    token = payload.bot_token or telegram_service.bot_token
    if not token:
        raise HTTPException(status_code=400, detail="Bot token is required")

    result = await telegram_service.verify_bot_token(token)
    if not result.get("valid"):
        raise HTTPException(status_code=400, detail=result.get("error", "Invalid Telegram bot token"))

    return {
        "status": "success",
        "bot_username": result.get("bot_username"),
        "bot_name": result.get("bot_name")
    }

@router.post("/telegram/detect-chat-id")
async def detect_telegram_chat_id(payload: TelegramDetectRequest):
    """Auto-detect Chat ID by inspecting recent bot messages via getUpdates."""
    token = payload.bot_token or telegram_service.bot_token
    if not token:
        raise HTTPException(status_code=400, detail="Bot token is required to detect chat ID")

    res = await telegram_service.detect_chat_id(token)
    if not res.get("success"):
        return {
            "status": "not_found",
            "message": res.get("message") or res.get("error") or "No messages detected"
        }

    return {
        "status": "success",
        "chat_id": res.get("chat_id"),
        "username": res.get("username"),
        "first_name": res.get("first_name")
    }

@router.post("/telegram/save", response_model=TelegramStatusResponse)
async def save_telegram_config(
    payload: TelegramConfigRequest,
    db: Session = Depends(get_db)
):
    """Save full Telegram bot token, chat ID, and notification times."""
    # Validate token first
    token = payload.bot_token.strip()
    chat_id = payload.chat_id.strip()

    if not token or not chat_id:
        raise HTTPException(status_code=400, detail="Both bot token and chat ID are required")

    bot_check = await telegram_service.verify_bot_token(token)
    if not bot_check.get("valid"):
        raise HTTPException(status_code=400, detail=f"Invalid Bot Token: {bot_check.get('error')}")

    # Upsert DB records
    upsert_map = {
        "TELEGRAM_BOT_TOKEN": token,
        "TELEGRAM_CHAT_ID": chat_id,
        "DAILY_DIGEST_TIME": payload.daily_digest_time or "08:30",
        "POSTING_REMINDER_TIME": payload.posting_reminder_time or "17:00",
        "ENABLE_SCHEDULER": "true"
    }

    for k, v in upsert_map.items():
        rec = db.query(AppSetting).filter(AppSetting.key == k).first()
        if not rec:
            rec = AppSetting(key=k, value=v, description=f"Configuration for {k}")
            db.add(rec)
        else:
            rec.value = v

    db.commit()

    # Update in-memory service
    telegram_service.bot_token = token
    telegram_service.chat_id = chat_id

    return TelegramStatusResponse(
        is_configured=True,
        bot_token_masked=_mask_value("TOKEN", token),
        chat_id=chat_id,
        bot_username=bot_check.get("bot_username"),
        bot_name=bot_check.get("bot_name"),
        daily_digest_time=payload.daily_digest_time or "08:30",
        posting_reminder_time=payload.posting_reminder_time or "17:00"
    )

@router.post("/telegram/test")
async def test_telegram_connection_detailed():
    """Send live test ping message to the user's Telegram."""
    if not telegram_service.is_configured():
        raise HTTPException(
            status_code=400,
            detail="Telegram is not configured. Please save your Bot Token and Chat ID first."
        )

    msg = (
        "📡 <b>ATH Radar — Connection Verified!</b>\n\n"
        "Your Telegram integration is now online and connected.\n"
        "You will receive:\n"
        "• <b>Daily Curated Digest:</b> Morning briefing of radar ideas\n"
        "• <b>Posting Reminders:</b> Nudges to polish & share insights\n\n"
        "<i>Ready to ship high-impact content!</i>"
    )
    success, message = await telegram_service.send_message_detailed(msg)
    if not success:
        raise HTTPException(status_code=400, detail=f"Telegram delivery failed: {message}")

    return {
        "status": "success",
        "message": "Verification message delivered directly to your Telegram!"
    }

@router.post("/telegram/send-digest")
async def send_digest_now(db: Session = Depends(get_db)):
    """Manually dispatch today's curated ideas digest to Telegram right now."""
    if not telegram_service.is_configured():
        raise HTTPException(status_code=400, detail="Telegram is not configured yet.")

    ideas = db.query(ContentIdea).filter(
        ContentIdea.is_editor_approved == True,
        ContentIdea.status != "skipped"
    ).order_by(ContentIdea.final_score.desc()).limit(5).all()

    if not ideas:
        raise HTTPException(status_code=404, detail="No approved ideas found to send in today's digest.")

    ideas_dict = [
        {
            "title": i.title,
            "hook": i.hook,
            "angle": i.angle,
            "personal_connection": i.personal_connection,
            "suggested_format": i.suggested_format
        }
        for i in ideas
    ]

    success = await telegram_service.send_daily_digest(ideas_dict)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to dispatch daily digest to Telegram.")

    return {
        "status": "success",
        "message": f"Successfully sent daily digest with {len(ideas)} ideas to Telegram!"
    }
