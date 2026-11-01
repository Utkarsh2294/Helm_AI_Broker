"""Async drivers for new operational routes; retain the core transaction hooks.

SQLAlchemy run_sync runs shared ORM helpers in its greenlet bridge. Database IO
uses asyncpg/aiosqlite; the established synchronous case service stays unchanged.
"""

import inspect
import asyncio
from functools import wraps
from fastapi import APIRouter, Depends
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

_engines = {}


async def close_engines():
    loop = asyncio.get_running_loop()
    for key in [key for key in _engines if key[0] is loop]:
        await _engines.pop(key).dispose()


async def database():
    from app import main

    # Resolve the current factory, including isolated QA/test databases.
    with main.SessionLocal() as probe:
        url = make_url(probe.get_bind().url)
    driver = "sqlite+aiosqlite" if url.get_backend_name() == "sqlite" else "postgresql+asyncpg"
    key = (asyncio.get_running_loop(), url)
    if key not in _engines:
        options = (
            {"poolclass": NullPool}
            if driver.startswith("sqlite")
            else {"pool_size": 5, "max_overflow": 5, "pool_pre_ping": True}
        )
        _engines[key] = create_async_engine(url.set(drivername=driver), **options)
    engine = _engines[key]
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        try:
            if driver.startswith("sqlite"):
                from sqlalchemy import text

                await db.execute(text("PRAGMA foreign_keys=ON"))
                await db.execute(text("PRAGMA busy_timeout=10000"))
            yield db
            await db.commit()
        except BaseException:
            await db.rollback()
            raise


def asynchronous(function):
    signature = inspect.signature(function, eval_str=True)
    parameters = [
        parameter.replace(default=Depends(database, scope="function")) if name == "db" else parameter
        for name, parameter in signature.parameters.items()
    ]

    @wraps(function)
    async def call(**kwargs):
        context = kwargs.get("ctx")
        db = kwargs.get("db") or getattr(context, "async_db", None)
        if db is None:
            raise RuntimeError("An asynchronous operational route needs its database context")

        def execute(sync_db):
            if "db" in kwargs:
                kwargs["db"] = sync_db
            if context is not None:
                context.db = sync_db
            return function(**kwargs)

        result = await db.run_sync(execute)
        if hasattr(result, "db"):
            result.async_db = db
        return result

    call.__signature__ = signature.replace(parameters=parameters)
    return call


class OperationalRouter(APIRouter):
    def add_api_route(self, path, endpoint, **kwargs):
        # Adapt registration, preserving ordinary helpers for worker/dashboard reuse.
        return super().add_api_route(path, asynchronous(endpoint), **kwargs)
