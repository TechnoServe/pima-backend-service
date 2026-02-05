from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from app.core.config import settings

def create_engine():
    # Use asyncpg driver. DATABASE_URL can be postgresql://...; convert if needed.
    url = settings.database_url
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # In production, prefer default pool; in dev, keep it simple.
    engine = create_async_engine(url, pool_pre_ping=True)
    return engine

engine = create_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
