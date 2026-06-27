import asyncio
from app.db.session import AsyncSession, engine
from app.services.monitoring import seed_devices
from sqlmodel import select
from app.db.models import Device

async def main():
    async with AsyncSession(engine) as session:
        await seed_devices(session)
        result = await session.exec(select(Device).order_by(Device.id).limit(20))
        rows = result.all()
        for row in rows:
            print(row)

if __name__ == '__main__':
    asyncio.run(main())
