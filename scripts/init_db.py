"""
数据库初始化脚本。
运行: python -m scripts.init_db
创建所有表并插入示例数据。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_engine, init_db
from core.models import Base, Device, Employee, Room, ToiletStall
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def seed_sample_data():
    """插入示例数据，仅在数据库为空时执行。"""
    engine = get_engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        from sqlalchemy import select, func
        count = await session.execute(select(func.count()).select_from(Room))
        if count.scalar() > 0:
            print("Database already has data, skipping seed.")
            return

        rooms = [
            Room(id="entrance", name="大门入口"),
            Room(id="zone_a", name="A区办公区", capacity=20),
            Room(id="meeting_1", name="1号会议室", capacity=10),
        ]
        session.add_all(rooms)

        devices = [
            Device(id="screen_entrance", name="入口屏幕", device_type="screen", room_id="entrance", protocol="mqtt"),
            Device(id="light_a1", name="A区灯光1", device_type="light", room_id="zone_a", protocol="mqtt"),
            Device(id="light_a2", name="A区灯光2", device_type="light", room_id="zone_a", protocol="mqtt"),
            Device(id="light_a3", name="A区灯光3", device_type="light", room_id="zone_a", protocol="mqtt"),
            Device(id="ac_a1", name="A区空调", device_type="ac", room_id="zone_a", protocol="mqtt"),
            Device(id="screen_a1", name="A区屏幕", device_type="screen", room_id="zone_a", protocol="mqtt"),
            Device(id="light_m1", name="会议室灯光", device_type="light", room_id="meeting_1", protocol="mqtt"),
            Device(id="ac_m1", name="会议室空调", device_type="ac", room_id="meeting_1", protocol="mqtt"),
            Device(id="screen_m1", name="会议室屏幕", device_type="screen", room_id="meeting_1", protocol="mqtt"),
        ]
        session.add_all(devices)

        employees = [
            Employee(id="emp_001", name="张三", email="zhangsan@example.com"),
            Employee(id="emp_002", name="李四", email="lisi@example.com"),
        ]
        session.add_all(employees)

        stalls = [
            ToiletStall(id="stall_3f_1", floor="3F", gender="male"),
            ToiletStall(id="stall_3f_2", floor="3F", gender="male"),
            ToiletStall(id="stall_3f_3", floor="3F", gender="female"),
            ToiletStall(id="stall_3f_4", floor="3F", gender="female"),
        ]
        session.add_all(stalls)

        await session.commit()
        print("Sample data inserted successfully.")


async def main():
    Path("data").mkdir(exist_ok=True)
    print("Initializing database...")
    await init_db()
    print("Tables created.")

    await seed_sample_data()
    print("Database initialization complete.")


if __name__ == "__main__":
    asyncio.run(main())
