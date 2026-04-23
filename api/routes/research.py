"""Standalone endpoint для ResearcherAgent."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from agents.researcher import ResearcherAgent
from core.llm_router import LLMRouter

router = APIRouter()
researcher_agent = ResearcherAgent(LLMRouter())


class ResearchRequest(BaseModel):
    query: str
    role: str = "pto_engineer"
    context: str = ""
    session_id: str | None = None


class ResearchApiResponse(BaseModel):
    session_id: str
    research_facts: str
    research_payload: dict


@router.post("/research", response_model=ResearchApiResponse)
async def research(payload: ResearchRequest) -> ResearchApiResponse:
    session_id = payload.session_id or str(uuid.uuid4())
    state = {
        "message": payload.query,
        "role": payload.role,
        "context": payload.context,
        "session_id": session_id,
        "history": [],
    }
    result = await researcher_agent.run(state)
    return ResearchApiResponse(
        session_id=session_id,
        research_facts=str(result.get("research_facts", "")),
        research_payload=dict(result.get("research_payload", {})),
    )
