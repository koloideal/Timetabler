from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def new_session_maker(db_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        db_url,
        pool_size=10,
        max_overflow=10,
        connect_args={
            "timeout": 5,
        },
    )
    return async_sessionmaker(engine, class_=AsyncSession, autoflush=False, expire_on_commit=False)
