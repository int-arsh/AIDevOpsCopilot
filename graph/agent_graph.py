"""LangGraph wiring for the AI DevOps Copilot multi-agent pipeline.

This module assembles the monitor, log analysis, runbook, and GitHub agents
into a single StateGraph, exposes a helper for running the pipeline, and
provides a small command-line entry point for local testing.
"""

import asyncio
from pprint import pprint

from langgraph.graph import END, StateGraph

from agents.github_agent import github_agent
from agents.log_analyser_agent import log_analyser_agent
from agents.monitor_agent import monitor_agent
from agents.runbook_agent import runbook_agent
from graph.state import CopilotState, initial_state


def build_graph():
	"""Build and compile the LangGraph pipeline for incident analysis."""

	graph = StateGraph(CopilotState)
	graph.add_node("monitor", monitor_agent)
	graph.add_node("log_analyse", log_analyser_agent)
	graph.add_node("runbook", runbook_agent)
	graph.add_node("github", github_agent)

	graph.set_entry_point("monitor")

	def route_after_monitor(state: CopilotState) -> str:
		"""Route the pipeline based on the monitor outcome."""

		if state.get("current_step") == "no_issues_found":
			return END
		if state.get("current_step") == "monitor_failed":
			return END
		return "log_analyse"

	graph.add_conditional_edges(
		"monitor",
		route_after_monitor,
		{
			END: END,
			"log_analyse": "log_analyse",
		},
	)

	graph.add_edge("log_analyse", "runbook")
	graph.add_edge("runbook", "github")
	graph.add_edge("github", END)

	return graph.compile()


async def run_pipeline(namespace: str = "default") -> CopilotState:
	"""Run the compiled LangGraph pipeline for the requested namespace."""

	graph = build_graph()
	state = initial_state()
	state["namespace"] = namespace
	final_state = await graph.ainvoke(state)
	return final_state


if __name__ == "__main__":
	final_state = asyncio.run(run_pipeline("default"))
	pprint(final_state)
