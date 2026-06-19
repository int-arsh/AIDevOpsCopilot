"""End-to-end tests for the LangGraph incident pipeline."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graph import agent_graph


def _crashing_pods_payload() -> list[dict[str, str]]:
    """Build a fake crashing pod list for the monitor agent."""

    return [
        {
            "namespace": "default",
            "name": "api-1",
            "ready": "0/1",
            "status": "CrashLoopBackOff",
            "restarts": "4",
            "age": "10m",
        },
        {
            "namespace": "default",
            "name": "worker-2",
            "ready": "0/1",
            "status": "OOMKilled",
            "restarts": "2",
            "age": "8m",
        },
    ]


def _pending_and_crashing_pods_payload() -> list[dict[str, str]]:
    """Build a fake crashing pod list that includes a Pending pod."""

    return [
        {
            "namespace": "default",
            "name": "pending-api",
            "ready": "0/1",
            "status": "Pending",
            "restarts": "0",
            "age": "1m",
        },
        {
            "namespace": "default",
            "name": "worker-2",
            "ready": "0/1",
            "status": "OOMKilled",
            "restarts": "2",
            "age": "8m",
        },
    ]


def _anomalies_payload() -> dict:
    """Build a fake Prometheus anomaly payload for the monitor agent."""

    return {
        "cpu": {"error": False, "data": []},
        "memory": {
            "error": False,
            "data": [
                {
                    "container": "api",
                    "pod": "api-1",
                    "namespace": "default",
                    "memory_ratio": 0.91,
                    "memory_percent": 91.0,
                }
            ],
        },
        "restarts": {"error": False, "data": []},
    }


async def _fake_github_agent(state: dict) -> dict:
    """Simulate successful GitHub issue creation without calling GitHub."""

    state["github_issue_url"] = "https://github.com/example/repo/issues/42"
    state["current_step"] = "complete"
    return state


@pytest.mark.asyncio
@patch("agents.monitor_agent.get_crashing_pods")
@patch("agents.monitor_agent.get_anomalies", new_callable=AsyncMock)
@patch("agents.log_analyser_agent.describe_pod")
@patch("agents.log_analyser_agent.get_pod_logs")
@patch("agents.log_analyser_agent.ask_groq", new_callable=AsyncMock)
@patch("agents.runbook_agent.ask_groq", new_callable=AsyncMock)
@patch.object(agent_graph, "github_agent", new=_fake_github_agent)
async def test_pipeline_success(
    mock_runbook_groq: AsyncMock,
    mock_log_groq: AsyncMock,
    mock_get_pod_logs: MagicMock,
    mock_describe_pod: MagicMock,
    mock_get_anomalies: AsyncMock,
    mock_get_crashing_pods: MagicMock,
) -> None:
    """Runs the full pipeline with mocked agents and asserts the final state."""

    mock_get_crashing_pods.return_value = {
        "error": False,
        "data": _crashing_pods_payload(),
    }
    mock_get_anomalies.return_value = {
        "error": False,
        "data": _anomalies_payload(),
    }
    mock_get_pod_logs.side_effect = [
        {"error": False, "data": "api-1 terminated with OOMKilled\n"},
        {"error": False, "data": "worker-2 terminated with OOMKilled\n"},
    ]
    mock_describe_pod.return_value = {"error": False, "data": ""}
    mock_log_groq.side_effect = [
        "The application is failing with OOMKilled errors in the API container.",
        "The most likely root cause is memory pressure from the API container.",
    ]
    mock_runbook_groq.return_value = (
        "## Incident Summary\n\nOOMKilled incident runbook generated."
    )

    state = await agent_graph.run_pipeline("default")

    assert len(state["crashing_pods"]) == 2
    assert state["analysis"]
    assert state["runbook"]
    assert state["current_step"] == "complete"
    assert state["github_issue_url"] == "https://github.com/example/repo/issues/42"


@pytest.mark.asyncio
@patch("agents.monitor_agent.get_crashing_pods")
@patch("agents.monitor_agent.get_anomalies", new_callable=AsyncMock)
@patch("agents.log_analyser_agent.describe_pod")
@patch("agents.log_analyser_agent.get_pod_logs")
@patch("agents.log_analyser_agent.ask_groq", new_callable=AsyncMock)
@patch("agents.runbook_agent.ask_groq", new_callable=AsyncMock)
@patch.object(agent_graph, "github_agent", new=_fake_github_agent)
async def test_pipeline_pending_pod_uses_describe_output(
    mock_runbook_groq: AsyncMock,
    mock_log_groq: AsyncMock,
    mock_get_pod_logs: MagicMock,
    mock_describe_pod: MagicMock,
    mock_get_anomalies: AsyncMock,
    mock_get_crashing_pods: MagicMock,
) -> None:
    """Uses describe output instead of logs for Pending pods."""

    mock_get_crashing_pods.return_value = {
        "error": False,
        "data": _pending_and_crashing_pods_payload(),
    }
    mock_get_anomalies.return_value = {
        "error": False,
        "data": _anomalies_payload(),
    }
    mock_get_pod_logs.return_value = {
        "error": False,
        "data": "worker-2 terminated with OOMKilled\n",
    }
    mock_describe_pod.return_value = {
        "error": False,
        "data": "Name: pending-api\nEvents:\n  Warning  FailedScheduling  1m  default-scheduler  0/1 nodes are available\n",
    }
    mock_log_groq.side_effect = [
        "The pending pod is failing to schedule and the other pod is OOMKilled.",
        "The most likely root cause is insufficient resources for scheduling and memory pressure.",
    ]
    mock_runbook_groq.return_value = (
        "## Incident Summary\n\nPending pod incident runbook generated."
    )

    state = await agent_graph.run_pipeline("default")

    assert state["current_step"] == "complete"
    assert mock_get_pod_logs.call_count == 1
    mock_describe_pod.assert_called_once_with("pending-api", "default")
    assert "Pod Description (Pending pod):" in mock_log_groq.await_args.kwargs["user_message"]


@pytest.mark.asyncio
@patch("agents.monitor_agent.get_crashing_pods")
@patch("agents.monitor_agent.get_anomalies", new_callable=AsyncMock)
@patch.object(agent_graph, "github_agent", new=_fake_github_agent)
async def test_pipeline_no_issues_found(
    mock_get_anomalies: AsyncMock,
    mock_get_crashing_pods: MagicMock,
) -> None:
    """Stops the pipeline early when the monitor finds no issues."""

    mock_get_crashing_pods.return_value = {"error": False, "data": []}
    mock_get_anomalies.return_value = {
        "error": False,
        "data": {
            "cpu": {"error": False, "data": []},
            "memory": {"error": False, "data": []},
            "restarts": {"error": False, "data": []},
        },
    }

    state = await agent_graph.run_pipeline("default")

    assert state["current_step"] == "no_issues_found"