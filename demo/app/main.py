import os
from functools import lru_cache
from typing import Annotated

import anthropic
from fastapi import Depends, FastAPI, HTTPException

from demo_shop.store import default_store

from .contract import AskRequest, AskResponse
from .copilot import Copilot
from .llm import AnthropicDiagnoser, LLMError

app = FastAPI(title="On-call Copilot")


@lru_cache(maxsize=1)
def get_copilot() -> Copilot:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "ANTHROPIC_API_KEY is not set: copy .env.example to .env and add the key")
    return Copilot(default_store(), AnthropicDiagnoser())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": os.getenv("APP_VERSION", "dev")}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, copilot: Annotated[Copilot, Depends(get_copilot)]) -> AskResponse:
    # dry_run is always honoured: v1 never executes anything, it only proposes actions.
    try:
        return copilot.ask(req.input)
    except (anthropic.APIError, LLMError) as exc:
        raise HTTPException(502, f"model call failed: {type(exc).__name__}: {exc}") from exc
