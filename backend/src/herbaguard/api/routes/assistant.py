"""AI evidence assistant (Phase 5): grounded answers with validated citations."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from herbaguard.ai.llm import ChatModel, Embedder
from herbaguard.api.schemas.assistant import AssistantRequest, AssistantResponse, AssistantStatus
from herbaguard.api.schemas.common import ErrorResponse
from herbaguard.core.config import Settings, get_settings
from herbaguard.core.db import get_session
from herbaguard.services import assistant as assistant_service

router = APIRouter(prefix="/assistant", tags=["assistant"])
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_chat_model(settings: SettingsDep) -> ChatModel | None:
    return assistant_service.chat_model_for(settings)


def get_embedder(settings: SettingsDep) -> Embedder | None:
    return assistant_service.embedder_for(settings)


@router.post(
    "/ask",
    response_model=AssistantResponse,
    summary="Answer a question from HerbaGuard's sources, with validated citations",
    description=(
        "Interaction classes in the answer come from the deterministic rules (same as "
        "`POST /interactions/check`); the local LLM only explains retrieved passages. Every "
        "citation marker is checked against the retrieved passages; answers that fail are "
        "regenerated once and otherwise replaced by verbatim quotes (`mode: extractive`). "
        "Dosing and emergency questions are answered with fixed referral texts. Not medical advice."
    ),
    responses={422: {"model": ErrorResponse}},
)
def ask(
    session: SessionDep,
    settings: SettingsDep,
    body: AssistantRequest,
    chat_model: Annotated[ChatModel | None, Depends(get_chat_model)],
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
) -> AssistantResponse:
    return assistant_service.ask(session, settings, body, chat_model=chat_model, embedder=embedder)


@router.get(
    "/status",
    response_model=AssistantStatus,
    summary="LLM provider, model availability and embedding coverage",
)
def status(session: SessionDep, settings: SettingsDep) -> AssistantStatus:
    return assistant_service.status(session, settings)
