from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from redis import Redis

from knowagent.agent.api.router import router as agent_router
from knowagent.common.errors import KnowAgentError
from knowagent.documents.api.router import router as documents_router
from knowagent.documents.infrastructure.sqlalchemy_repository import (
    SqlAlchemyIngestionCoordinator,
)
from knowagent.identity.api.router import router as identity_router
from knowagent.platform.database import create_database_engine, create_session_factory
from knowagent.platform.settings import Settings
from knowagent.systems.api.router import router as systems_router
from knowagent.tickets.api.router import router as tickets_router
from knowagent.worker.celery_app import build_celery_app
from knowagent.worker.dispatcher import CeleryIngestionDispatcher

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


class ApiErrorView(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, str | int | bool] | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_environment()
    application = FastAPI(title="KnowAgent API", version="0.1.0")
    engine = create_database_engine(resolved_settings.database_url)
    application.state.settings = resolved_settings
    application.state.engine = engine
    application.state.session_factory = create_session_factory(engine)
    application.state.object_store = None
    application.state.ingestion_coordinator = SqlAlchemyIngestionCoordinator(
        application.state.session_factory
    )
    application.state.ingestion_dispatcher = CeleryIngestionDispatcher(
        build_celery_app(resolved_settings)
    )
    application.state.redis_client = Redis.from_url(
        resolved_settings.redis_url,
        decode_responses=True,
    )

    @application.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied_request_id = request.headers.get("X-Request-ID", "")
        if _REQUEST_ID_PATTERN.fullmatch(supplied_request_id):
            request.state.request_id = supplied_request_id
        else:
            request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @application.exception_handler(KnowAgentError)
    async def handle_known_error(request: Request, error: KnowAgentError) -> JSONResponse:
        payload = ApiErrorView(
            code=error.code,
            message=error.message,
            request_id=request.state.request_id,
            details=error.details,
        )
        return JSONResponse(status_code=error.status_code, content=payload.model_dump(mode="json"))

    @application.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(agent_router, prefix="/api/v1")
    application.include_router(identity_router, prefix="/api/v1")
    application.include_router(systems_router, prefix="/api/v1")
    application.include_router(documents_router, prefix="/api/v1")
    application.include_router(tickets_router, prefix="/api/v1")
    return application


app = create_app()
