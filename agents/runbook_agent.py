"""LangGraph runbook agent for the AI DevOps Copilot workflow.

This node runs after log analysis has identified the most likely root cause. It
uses Groq to generate a practical Kubernetes incident runbook with immediate
remediation steps, verification commands, and prevention guidance, then stores
the result in the shared ``CopilotState`` for downstream use.
"""

from graph.state import CopilotState
from utils.groq_client import ask_groq


SYSTEM_PROMPT = (
	"You are a senior SRE (Site Reliability Engineer).\n"
	"Generate clear, actionable runbooks for Kubernetes incidents.\n"
	"Format your response in markdown with these sections:\n"
	"## Incident Summary\n"
	"## Root Cause\n"
	"## Immediate Actions (numbered steps)\n"
	"## Verification Steps\n"
	"## Prevention"
)


async def runbook_agent(state: CopilotState) -> CopilotState:
	"""Generate an operational runbook for the incident represented in state.

	The runbook agent is the third node in the LangGraph pipeline. It reads the
	crashing pods, root cause, log analysis, and Prometheus anomalies from the
	shared state, then asks Groq to produce a concise markdown runbook with
	specific Kubernetes remediation commands where relevant. Any exception is
	captured in ``state['error']`` and marks the step as ``runbook_failed``.
	"""

	print("Runbook Agent starting...")

	try:
		print("Runbook Agent: generating runbook from incident data...")
		runbook = await ask_groq(
			system_prompt=SYSTEM_PROMPT,
			user_message=(
				"Generate a runbook for this incident:\n\n"
				f"Crashing Pods: {state['crashing_pods']}\n"
				f"Root Cause: {state['root_cause']}\n"
				f"Analysis: {state['analysis']}\n"
				f"Prometheus Anomalies: {state['anomalies']}\n\n"
				"Make steps specific with exact kubectl commands where relevant."
			),
		)

		state["runbook"] = runbook
		state["current_step"] = "runbook_complete"
		print("Runbook Agent: runbook generation complete")
		return state
	except Exception as exc:
		state["error"] = str(exc)
		state["current_step"] = "runbook_failed"
		print(f"Runbook Agent failed: {exc}")
		return state
