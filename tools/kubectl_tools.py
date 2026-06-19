"""Structured kubectl helpers invoked by agents for cluster inspection."""

import json
import subprocess
from typing import Any

from tools.k8s_auth import get_kubectl_env


def get_all_pods(namespace: str = "all") -> dict:
    """Fetch pods from the cluster and return name, namespace, status, and restart count."""
    try:
        if namespace == "all":
            cmd = ["kubectl", "get", "pods", "--all-namespaces", "-o", "json"]
        else:
            cmd = ["kubectl", "get", "pods", "-n", namespace, "-o", "json"]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            env=get_kubectl_env(),
        )

        payload = json.loads(result.stdout)
        pods: list[dict[str, Any]] = []

        for item in payload.get("items", []):
            metadata = item.get("metadata", {})
            status_block = item.get("status", {})
            container_statuses = status_block.get("containerStatuses") or []

            status = status_block.get("phase", "Unknown")
            for cs in container_statuses:
                state = cs.get("state", {})
                waiting = state.get("waiting", {})
                terminated = state.get("terminated", {})
                if waiting.get("reason"):
                    status = waiting["reason"]
                    break
                if terminated.get("reason"):
                    status = terminated["reason"]
                    break

            restart_count = sum(cs.get("restartCount", 0) for cs in container_statuses)

            pods.append(
                {
                    "name": metadata.get("name", ""),
                    "namespace": metadata.get("namespace", ""),
                    "status": status,
                    "restartCount": restart_count,
                }
            )

        return {"error": False, "data": pods}
    except Exception as e:
        return {"error": True, "message": str(e), "output": ""}


def describe_pod(pod_name: str, namespace: str = "default") -> dict:
    """Describe a pod and return the raw kubectl describe output."""
    try:
        result = subprocess.run(
            ["kubectl", "describe", "pod", pod_name, "-n", namespace],
            capture_output=True,
            text=True,
            check=True,
            env=get_kubectl_env(),
        )

        return {"error": False, "data": result.stdout}
    except Exception as e:
        return {"error": True, "message": str(e), "output": ""}


def get_pod_logs(
    pod_name: str,
    namespace: str = "default",
    previous: bool = True,
    pod_status: str = "",
) -> dict:
    """Fetch the last 100 lines of logs for a pod.

    The helper prefers the current container logs first, then falls back to
    ``--previous`` when requested and the current logs are empty. Pending pods
    are skipped entirely because they have not started a container yet.
    """
    try:
        if pod_status == "Pending":
            return {
                "error": False,
                "data": "",
                "note": "Pod is in Pending state, no container has started yet.",
            }

        current_cmd = ["kubectl", "logs", pod_name, "-n", namespace, "--tail=100"]
        current_result = subprocess.run(
            current_cmd,
            capture_output=True,
            text=True,
            check=True,
            env=get_kubectl_env(),
        )

        current_logs = current_result.stdout
        if current_logs.strip() or not previous:
            return {"error": False, "data": current_logs}

        previous_cmd = current_cmd + ["--previous"]
        previous_result = subprocess.run(
            previous_cmd,
            capture_output=True,
            text=True,
            check=True,
            env=get_kubectl_env(),
        )

        return {"error": False, "data": previous_result.stdout}
    except Exception as e:
        return {"error": True, "message": str(e), "output": ""}


def get_node_resources() -> dict:
    """Return CPU and memory usage for each node from kubectl top nodes."""
    try:
        result = subprocess.run(
            ["kubectl", "top", "nodes"],
            capture_output=True,
            text=True,
            check=True,
            env=get_kubectl_env(),
        )

        lines = result.stdout.strip().splitlines()
        if len(lines) < 2:
            return {"error": False, "data": []}

        nodes: list[dict[str, str]] = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 5:
                continue
            nodes.append(
                {
                    "name": parts[0],
                    "cpu_cores": parts[1],
                    "cpu_percent": parts[2],
                    "memory_bytes": parts[3],
                    "memory_percent": parts[4],
                }
            )

        return {"error": False, "data": nodes}
    except Exception as e:
        return {"error": True, "message": str(e), "output": ""}


def get_crashing_pods() -> dict:
    """Return pods in CrashLoopBackOff, Error, OOMKilled, or Pending state across all namespaces."""
    try:
        result = subprocess.run(
            ["kubectl", "get", "pods", "--all-namespaces"],
            capture_output=True,
            text=True,
            check=True,
            env=get_kubectl_env(),
        )

        crashing_statuses = {"CrashLoopBackOff", "Error", "OOMKilled", "Pending"}
        lines = result.stdout.strip().splitlines()
        crashing_pods: list[dict[str, str]] = []

        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 5:
                continue

            status = parts[3]
            if status in crashing_statuses:
                crashing_pods.append(
                    {
                        "namespace": parts[0],
                        "name": parts[1],
                        "ready": parts[2],
                        "status": status,
                        "restarts": parts[4],
                        "age": parts[5] if len(parts) > 5 else "",
                    }
                )

        return {"error": False, "data": crashing_pods}
    except Exception as e:
        return {"error": True, "message": str(e), "output": ""}


if __name__ == "__main__":
    import pprint

    pprint.pp(get_crashing_pods())
