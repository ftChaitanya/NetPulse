import asyncio
from app.db.session import AsyncSession, engine
from app.services.discovery import refresh_devices, discover_network
from sqlmodel import select
from app.db.models import Device

async def main():
    async with AsyncSession(engine) as session:
        refreshed = await refresh_devices(session)
        print('refreshed_count=', len(refreshed))
        for d in refreshed[:5]:
            print('REFRESH', d.ip_address, d.mac_address, d.vendor)

        discovered = await discover_network(cidr='192.168.1.0/30', session=session)
        print('discovered_count=', len(discovered))
        for d in discovered[:5]:
            print('DISCOVER', d.ip_address, d.mac_address, d.vendor)

if __name__ == '__main__':
    asyncio.run(main())
