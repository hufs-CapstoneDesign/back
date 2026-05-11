from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    connect_args={
        "ssl": False,
        "statement_cache_size": 0,  # Supabase PgBouncer 호환
    }
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session