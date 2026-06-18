"""LangGraph GitHub agent for the AI DevOps Copilot workflow.

This is the final node in the pipeline. It converts the incident context in
``CopilotState`` into a GitHub issue so operators have a persistent record of
the outage, the root cause analysis, and the suggested remediation runbook.
"""

from datetime import datetime, timezone
import os

from dotenv import load_dotenv
from github import Github

from graph.state import CopilotState

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")


async def github_agent(state: CopilotState) -> CopilotState:
    """Create a GitHub issue for the incident represented in state.

    The GitHub agent is the final node in the LangGraph pipeline. It uses the
    PyGithub library to open an issue in the repository configured by
    ``GITHUB_REPO`` and stores the resulting issue URL in
    ``state['github_issue_url']``. If GitHub interaction fails for any reason,
    the pipeline does not crash; instead, a warning message is placed in
    ``state['error']`` and the state is returned to the caller.
    """

    print("GitHub Agent starting...")

    try:
        if not GITHUB_TOKEN:
            raise ValueError("GITHUB_TOKEN is not set. Add it to your .env file.")
        if not GITHUB_REPO:
            raise ValueError("GITHUB_REPO is not set. Add it to your .env file.")

        namespace = state.get("namespace", "")
        crashing_pods = state.get("crashing_pods", [])
        current_time = datetime.now(timezone.utc).isoformat()

        print(f"GitHub Agent: connecting to repo {GITHUB_REPO}")
        github_client = Github(GITHUB_TOKEN)
        repo = github_client.get_repo(GITHUB_REPO)

        title = (
            f"🚨 K8s Incident: {len(crashing_pods)} pod(s) crashing in {namespace}"
        )
        body = (
            "## Incident Report\n"
            f"**Namespace:** {namespace}\n"
            f"**Crashing Pods:** {crashing_pods}\n"
            f"**Detected At:** {current_time}\n\n"
            "## Root Cause\n"
            f"{state['root_cause']}\n\n"
            "## Analysis\n"
            f"{state['analysis']}\n\n"
            "---\n"
            f"{state['runbook']}"
        )

        issue = repo.create_issue(
            title=title,
            body=body,
            labels=["incident", "kubernetes", "auto-generated"],
        )

        state["github_issue_url"] = issue.html_url
        state["current_step"] = "complete"
        print(f"GitHub Agent: issue created at {issue.html_url}")
        return state
    except Exception as exc:
        warning_message = f"GitHub issue creation warning: {exc}"
        state["error"] = warning_message
        state["github_issue_url"] = state.get("github_issue_url", "")
        state["current_step"] = "complete"
        print(f"GitHub Agent warning: {exc}")
        return state