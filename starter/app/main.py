import os

from fastapi import FastAPI

from .contract import AskRequest, AskResponse

app = FastAPI(title="Capstone")  # TODO(starter): name of your project


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": os.getenv("APP_VERSION", "dev")}


@app.post("/ask", response_model=AskResponse, response_model_exclude_none=True)
def ask(req: AskRequest) -> AskResponse:
    # TODO(starter): stage 2 — replace with the simplest end-to-end path: input -> model -> answer.
    # With dry_run=True never perform irreversible actions, only return them in actions_proposed.
    return AskResponse(answer=f"Not implemented yet. Received {len(req.input)} characters.")
