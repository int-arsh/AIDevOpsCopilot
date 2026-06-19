"""FastAPI application entrypoint for the AI DevOps Copilot."""

import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from graph.agent_graph import run_pipeline
from tools.k8s_auth import is_in_cluster
from tools.kubectl_tools import get_crashing_pods
from tools.prometheus_tools import get_anomalies

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"

app = FastAPI(title="AI DevOps Copilot")


@app.on_event("startup")
def log_runtime_mode() -> None:
    """Log whether kubectl should use in-cluster or local auth."""

    print(f"Running in-cluster: {is_in_cluster()}")


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
async def analyze(request: AnalyzeRequest) -> dict:
    """Run the incident analysis pipeline for the requested namespace."""

    try:
        state = await run_pipeline(request.namespace)
        return {
            "status": "complete",
            "namespace": request.namespace,
            "crashing_pods": state["crashing_pods"],
            "root_cause": state["root_cause"],
            "runbook": state["runbook"],
            "github_issue_url": state["github_issue_url"],
            "current_step": state["current_step"],
            "error": state["error"],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
