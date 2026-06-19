"""LangGraph monitor agent for the AI DevOps Copilot workflow.

The monitor agent is the first node in the graph. It inspects the cluster for
crashing pods and Prometheus anomalies, then stores the results in
``CopilotState`` so downstream agents can analyze the incident, derive a root
cause, and generate remediation steps.
"""

import asyncio

from graph.state import CopilotState
from tools.kubectl_tools import get_crashing_pods
from tools.prometheus_tools import get_anomalies


def _has_anomaly_data(anomalies: dict) -> bool:
	"""Return True when the Prometheus payload contains at least one anomaly."""

	if anomalies.get("error"):
		return True

	data = anomalies.get("data", {})
	if not isinstance(data, dict):
		return bool(data)

	for value in data.values():
		if value.get("error"):
			return True
		entries = value.get("data", [])
		if entries:
			return True

	return False


async def monitor_agent(state: CopilotState) -> CopilotState:
	"""Inspect the cluster for crashing pods and Prometheus anomalies.

	The monitor agent is the first step in the LangGraph pipeline. It logs the
	namespace being checked, gathers pod crash information from kubectl,
	collects Prometheus anomaly data, and updates the shared state for the
	downstream analysis agents. If nothing suspicious is found, the step is
	marked as ``no_issues_found``. Any exception is captured in ``state['error']``
	and the step is marked ``monitor_failed``.
	"""

	namespace = state.get("namespace", "")
	print(f"Monitor Agent starting... namespace={namespace or 'all'}")

	try:
		print("Monitor Agent: checking for crashing pods...")
		crash_result = await asyncio.to_thread(get_crashing_pods)
		if crash_result.get("error"):
			raise RuntimeError(crash_result.get("message", "Failed to get crashing pods"))

		crashing_entries = crash_result.get("data", [])
		if namespace:
			crashing_entries = [
				pod for pod in crashing_entries if pod.get("namespace") == namespace
			]

		crashing_pod_names = [
			pod.get("name", "") for pod in crashing_entries if pod.get("name")
		]

		print("Monitor Agent: checking Prometheus anomalies...")
		anomalies_result = await get_anomalies()
		if anomalies_result.get("error"):
			raise RuntimeError(anomalies_result.get("message", "Failed to get anomalies"))

		anomalies_payload = anomalies_result.get("data", {})

		state["crashing_pods"] = crashing_entries
		state["anomalies"] = anomalies_payload
		state["current_step"] = "monitor_complete"

		print(f"Monitor Agent: crashing pods={crashing_pod_names}")
		print(f"Monitor Agent: anomalies found={_has_anomaly_data(anomalies_result)}")

		if not crashing_pod_names and not _has_anomaly_data(anomalies_result):
			state["current_step"] = "no_issues_found"
			print("Monitor Agent: no issues found in the cluster.")
		else:
			print("Monitor Agent: issues detected, handing off to downstream agents.")

		return state
	except Exception as exc:
		state["error"] = str(exc)
		state["current_step"] = "monitor_failed"
		print(f"Monitor Agent failed: {exc}")
		return state
