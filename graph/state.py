"""Shared LangGraph state for the AI DevOps Copilot multi-agent workflow.

This state object carries the Kubernetes namespace being analyzed, live signals
from the monitor and log analysis agents, Groq-generated reasoning and runbook
content, and any GitHub issue URL or error captured while the workflow runs.
"""

from typing import TypedDict


class CopilotState(TypedDict):
    """State passed between LangGraph agents during a single analysis run."""

    namespace: str
    crashing_pods: list[dict[str, str]]
    raw_logs: dict
    anomalies: dict
    analysis: str
    root_cause: str
    runbook: str
    github_issue_url: str
    error: str
    current_step: str


def initial_state() -> CopilotState:
    """Return a fresh CopilotState populated with empty defaults."""

    return {
        "namespace": "",
        "crashing_pods": [],
        "raw_logs": {},
        "anomalies": {},
        "analysis": "",
        "root_cause": "",
        "runbook": "",
        "github_issue_url": "",
        "error": "",
        "current_step": "",
    }