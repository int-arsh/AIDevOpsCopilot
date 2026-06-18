"""Async Prometheus HTTP API query helpers for metrics used by the monitor agent."""

import asyncio
import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
HTTP_TIMEOUT = 10.0


def _extract_vector_results(prom_response: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse metric/value pairs from a Prometheus instant-query JSON response."""
    results = prom_response.get("data", {}).get("result", [])
    extracted: list[dict[str, Any]] = []

    for item in results:
        metric = item.get("metric", {})
        value_pair = item.get("value", [])
        value = float(value_pair[1]) if len(value_pair) > 1 else 0.0
        extracted.append({"metric": metric, "value": value})

    return extracted


async def query_prometheus(promql: str) -> dict:
    """Execute an instant PromQL query against the Prometheus HTTP API."""
    try:
        url = f"{PROMETHEUS_URL}/api/v1/query"
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(url, params={"query": promql})
            response.raise_for_status()
            payload = response.json()

        if payload.get("status") != "success":
            return {
                "error": True,
                "message": payload.get("error", "Prometheus query failed"),
            }

        return {"error": False, "data": payload}
    except Exception as exc:
        return {"error": True, "message": str(exc)}


async def get_cpu_usage() -> dict:
    """Return the top 10 containers by CPU usage rate over the last 5 minutes."""
    try:
        result = await query_prometheus(
            "rate(container_cpu_usage_seconds_total[5m])"
        )
        if result.get("error"):
            return result

        rows = _extract_vector_results(result["data"])
        rows.sort(key=lambda row: row["value"], reverse=True)
        top_containers = [
            {
                "container": row["metric"].get("container", ""),
                "pod": row["metric"].get("pod", ""),
                "namespace": row["metric"].get("namespace", ""),
                "cpu_rate": row["value"],
            }
            for row in rows[:10]
        ]

        return {"error": False, "data": top_containers}
    except Exception as exc:
        return {"error": True, "message": str(exc)}


async def get_memory_usage() -> dict:
    """Return containers using more than 70% of their memory limit."""
    try:
        result = await query_prometheus(
            "container_memory_usage_bytes / container_spec_memory_limit_bytes"
        )
        if result.get("error"):
            return result

        rows = _extract_vector_results(result["data"])
        high_memory = [
            {
                "container": row["metric"].get("container", ""),
                "pod": row["metric"].get("pod", ""),
                "namespace": row["metric"].get("namespace", ""),
                "memory_ratio": row["value"],
                "memory_percent": round(row["value"] * 100, 2),
            }
            for row in rows
            if row["value"] > 0.7
        ]

        return {"error": False, "data": high_memory}
    except Exception as exc:
        return {"error": True, "message": str(exc)}


async def get_pod_restart_rate() -> dict:
    """Return pods with more than 2 container restarts in the last hour."""
    try:
        result = await query_prometheus(
            "increase(kube_pod_container_status_restarts_total[1h])"
        )
        if result.get("error"):
            return result

        rows = _extract_vector_results(result["data"])
        restarting_pods = [
            {
                "container": row["metric"].get("container", ""),
                "pod": row["metric"].get("pod", ""),
                "namespace": row["metric"].get("namespace", ""),
                "restarts_last_hour": row["value"],
            }
            for row in rows
            if row["value"] > 2
        ]

        return {"error": False, "data": restarting_pods}
    except Exception as exc:
        return {"error": True, "message": str(exc)}


async def get_anomalies() -> dict:
    """Run CPU, memory, and restart checks and return combined anomaly results."""
    try:
        cpu_result = await get_cpu_usage()
        memory_result = await get_memory_usage()
        restart_result = await get_pod_restart_rate()

        return {
            "error": False,
            "data": {
                "cpu": cpu_result,
                "memory": memory_result,
                "restarts": restart_result,
            },
        }
    except Exception as exc:
        return {"error": True, "message": str(exc)}


if __name__ == "__main__":
    import pprint

    pprint.pp(asyncio.run(get_anomalies()))
