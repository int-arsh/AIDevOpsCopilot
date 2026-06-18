"""FastAPI application entrypoint for the AI DevOps Copilot."""

import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

from tools.kubectl_tools import get_crashing_pods
from tools.prometheus_tools import get_anomalies

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"

app = FastAPI(title="AI DevOps Copilot")


class AnalyzeRequest(BaseModel):
    """Request body for the cluster analysis endpoint."""

    namespace: str = Field(default="default", description="Kubernetes namespace to analyze")


@app.get("/health")
async def health() -> dict[str, str]:
    """Return application health and runtime configuration."""
    return {
        "status": "ok",
        "app_env": os.getenv("APP_ENV", ""),
        "groq_model": GROQ_MODEL,
    }


@app.post("/analyze")
async def analyze(request: AnalyzeRequest) -> dict[str, str]:
    """Accept a namespace and return a placeholder response until agents are wired."""
    return {
        "status": "agents not wired yet",
        "namespace": request.namespace,
    }


@app.get("/cluster/pods")
async def get_pods() -> dict:
    """Return pods in crash/error states across all namespaces."""
    return get_crashing_pods()


@app.get("/cluster/metrics")
async def get_metrics() -> dict:
    """Return anomalies detected in cluster metrics (CPU, memory, restarts)."""
    return await get_anomalies()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
