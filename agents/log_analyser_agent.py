"""LangGraph log analyser agent for the AI DevOps Copilot workflow.

This node runs after the monitor agent. It pulls the logs for the crashing pods
reported by the monitor, sends those logs to Groq for technical analysis, then
asks Groq to refine that analysis into the single most likely root cause using
the Prometheus anomaly data already stored in the shared state.
"""

import asyncio

from graph.state import CopilotState
from tools.kubectl_tools import describe_pod, get_pod_logs
from utils.groq_client import ask_groq


SYSTEM_PROMPT = (
	"You are a senior DevOps engineer and Kubernetes expert.\n"
	"Analyse the provided pod logs and identify:\n"
	"1. What error is occurring\n"
	"2. Which service or component is failing\n"
	"3. Severity: Critical / High / Medium / Low\n"
	"Be concise and technical."
)


async def log_analyser_agent(state: CopilotState) -> CopilotState:
	"""Inspect crashing pod logs and derive an incident analysis.

	The log analyser is the second node in the LangGraph pipeline. It reads the
	crashing pod list from ``state['crashing_pods']``, fetches logs for up to the
	first three pods in the configured namespace, stores the raw logs back into
	``state['raw_logs']``, and sends the combined logs to Groq for analysis.
	A second Groq call then narrows the result to the most likely root cause by
	considering both the log analysis and the Prometheus anomaly payload.
	Any exception is captured in ``state['error']`` and marks the step as
	``analysis_failed``.
	"""

	print("Log Analyser Agent starting...")

	try:
		namespace = state.get("namespace", "")
		crashing_pods = state.get("crashing_pods", [])[:3]
		raw_logs = state.get("raw_logs", {})

		print(f"Log Analyser Agent: namespace={namespace or 'default'}")
		print(f"Log Analyser Agent: processing up to {len(crashing_pods)} crashing pods")

		combined_logs_parts: list[str] = []

		for pod_entry in crashing_pods:
			if isinstance(pod_entry, dict):
				pod_name = pod_entry.get("name", "")
				pod_namespace = pod_entry.get("namespace") or namespace or "default"
				pod_status = pod_entry.get("status", "")
			else:
				pod_name = str(pod_entry)
				pod_namespace = namespace or "default"
				pod_status = ""

			if not pod_name:
				continue

			if pod_status == "Pending":
				print(f"Log Analyser Agent: describing pending pod={pod_name}")
				describe_result = await asyncio.to_thread(
					describe_pod,
					pod_name,
					pod_namespace,
				)

				if describe_result.get("error"):
					raise RuntimeError(
						describe_result.get(
							"message", f"Failed to describe pod {pod_name}"
						)
					)

				pod_description = describe_result.get("data", "")
				raw_logs[pod_name] = pod_description
				combined_logs_parts.append(
					f"=== {pod_name} ===\nPod Description (Pending pod):\n{pod_description}"
				)
				continue

			print(f"Log Analyser Agent: fetching logs for pod={pod_name}")
			logs_result = await asyncio.to_thread(
				get_pod_logs,
				pod_name,
				pod_namespace,
				True,
				pod_status,
			)

			if logs_result.get("error"):
				raise RuntimeError(
					logs_result.get("message", f"Failed to get logs for pod {pod_name}")
				)

			pod_logs = logs_result.get("data", "")
			raw_logs[pod_name] = pod_logs
			combined_logs_parts.append(f"=== {pod_name} ===\n{pod_logs}")

		state["raw_logs"] = raw_logs

		combined_logs = "\n\n".join(combined_logs_parts).strip()
		print("Log Analyser Agent: sending combined logs to Groq")

		analysis = await ask_groq(
			system_prompt=SYSTEM_PROMPT,
			user_message=(
				"Analyse these Kubernetes pod logs and find the root cause:\n"
				f"{combined_logs}"
			),
		)
		state["analysis"] = analysis

		print("Log Analyser Agent: refining root cause with Prometheus anomalies")
		root_cause = await ask_groq(
			system_prompt=SYSTEM_PROMPT,
			user_message=(
				f"Based on this analysis: {state['analysis']}\n"
				f"And these Prometheus anomalies: {state['anomalies']}\n"
				"What is the single most likely root cause? One paragraph max."
			),
		)
		state["root_cause"] = root_cause
		state["current_step"] = "analysis_complete"

		print("Log Analyser Agent: analysis complete")
		return state
	except Exception as exc:
		state["error"] = str(exc)
		state["current_step"] = "analysis_failed"
		print(f"Log Analyser Agent failed: {exc}")
		return state
