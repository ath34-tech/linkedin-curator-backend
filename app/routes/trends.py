from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.models import Trend, Connection
from app.schemas.schemas import TrendResponse, ConnectionResponse

router = APIRouter(prefix="/trends", tags=["Trends"])

@router.get("", response_model=List[TrendResponse])
def get_trends(
    category: Optional[str] = Query(None, description="emerging, rapidly_rising, stable, saturated"),
    db: Session = Depends(get_db)
):
    query = db.query(Trend)
    if category:
        query = query.filter(Trend.category == category)
    return query.order_by(Trend.heat_score.desc(), Trend.detected_at.desc()).all()

@router.get("/{id}", response_model=TrendResponse)
def get_trend(id: int, db: Session = Depends(get_db)):
    trend = db.query(Trend).filter(Trend.id == id).first()
    if not trend:
        raise HTTPException(status_code=404, detail="Trend not found")
    return trend

@router.get("/{id}/connections", response_model=List[ConnectionResponse])
def get_trend_connections(id: int, db: Session = Depends(get_db)):
    return db.query(Connection).filter(Connection.trend_id == id).all()
