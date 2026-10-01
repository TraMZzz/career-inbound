import os

from fastapi import FastAPI

app = FastAPI(title="On-call Copilot")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": os.getenv("APP_VERSION", "dev")}
