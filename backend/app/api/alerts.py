from fastapi import APIRouter, Depends
from sqlmodel import select
from app.db.models import Alert
from app.db.session import get_session
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter()

@router.get("/", response_model=list[Alert])
async def list_alerts(session: AsyncSession = Depends(get_session), active_only: bool = True):
    query = select(Alert).order_by(Alert.created_at.desc())
    if active_only:
        query = query.where(Alert.resolved == False)
    result = await session.exec(query)
    return result.all()
