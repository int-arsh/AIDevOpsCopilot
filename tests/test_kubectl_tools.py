"""Unit tests for kubectl_tools with mocked subprocess calls."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from tools.kubectl_tools import (
    describe_pod,
    get_all_pods,
    get_crashing_pods,
    get_node_resources,
    get_pod_logs,
)


def _success_result(stdout: str) -> MagicMock:
    """Build a mock CompletedProcess with the given stdout."""
    result = MagicMock()
    result.stdout = stdout
    result.returncode = 0
    return result


def _raise_called_process_error(*_args, **_kwargs) -> None:
    """Simulate kubectl failing with a non-zero exit code."""
    raise subprocess.CalledProcessError(
        returncode=1,
        cmd=["kubectl"],
        stderr="kubectl command failed",
    )


class TestGetAllPods:
    """Tests for get_all_pods."""

    @patch("tools.kubectl_tools.subprocess.run")
    def test_success_all_namespaces(self, mock_run: MagicMock) -> None:
        """Returns parsed pod list when kubectl succeeds."""
        payload = {
            "items": [
                {
                    "metadata": {"name": "app-1", "namespace": "default"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {"restartCount": 2, "state": {"running": {}}}
                        ],
                    },
                },
                {
                    "metadata": {"name": "app-2", "namespace": "kube-system"},
                    "status": {
                        "phase": "Pending",
                        "containerStatuses": [
                            {
                                "restartCount": 0,
                                "state": {"waiting": {"reason": "ContainerCreating"}},
                            }
                        ],
                    },
                },
            ]
        }
        mock_run.return_value = _success_result(json.dumps(payload))

        result = get_all_pods()

        assert result == {
            "error": False,
            "data": [
                {
                    "name": "app-1",
                    "namespace": "default",
                    "status": "Running",
                    "restartCount": 2,
                },
                {
                    "name": "app-2",
                    "namespace": "kube-system",
                    "status": "ContainerCreating",
                    "restartCount": 0,
                },
            ],
        }
        mock_run.assert_called_once_with(
            ["kubectl", "get", "pods", "--all-namespaces", "-o", "json"],
            capture_output=True,
            text=True,
            check=True,
        )

    @patch("tools.kubectl_tools.subprocess.run")
    def test_failure(self, mock_run: MagicMock) -> None:
        """Returns structured error when kubectl fails."""
        mock_run.side_effect = _raise_called_process_error

        result = get_all_pods()

        assert result["error"] is True
        assert "kubectl command failed" in result["message"] or "returned non-zero" in result["message"]
        assert result["output"] == ""


class TestDescribePod:
    """Tests for describe_pod."""

    @patch("tools.kubectl_tools.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        """Returns raw describe output when kubectl succeeds."""
        describe_output = "Name: my-pod\nNamespace: default\nStatus: Running\n"
        mock_run.return_value = _success_result(describe_output)

        result = describe_pod("my-pod", namespace="staging")

        assert result == {"error": False, "data": describe_output}
        mock_run.assert_called_once_with(
            ["kubectl", "describe", "pod", "my-pod", "-n", "staging"],
            capture_output=True,
            text=True,
            check=True,
        )

    @patch("tools.kubectl_tools.subprocess.run")
    def test_failure(self, mock_run: MagicMock) -> None:
        """Returns structured error when describe fails."""
        mock_run.side_effect = _raise_called_process_error

        result = describe_pod("missing-pod")

        assert result["error"] is True
        assert result["message"]
        assert result["output"] == ""


class TestGetPodLogs:
    """Tests for get_pod_logs."""

    @patch("tools.kubectl_tools.subprocess.run")
    def test_success_with_previous(self, mock_run: MagicMock) -> None:
        """Returns log output including --previous flag by default."""
        log_output = "line 1\nline 2\nerror: connection refused\n"
        mock_run.return_value = _success_result(log_output)

        result = get_pod_logs("my-pod", namespace="prod", previous=True)

        assert result == {"error": False, "data": log_output}
        mock_run.assert_called_once_with(
            ["kubectl", "logs", "my-pod", "-n", "prod", "--tail=100", "--previous"],
            capture_output=True,
            text=True,
            check=True,
        )

    @patch("tools.kubectl_tools.subprocess.run")
    def test_failure(self, mock_run: MagicMock) -> None:
        """Returns structured error when log retrieval fails."""
        mock_run.side_effect = _raise_called_process_error

        result = get_pod_logs("my-pod")

        assert result["error"] is True
        assert result["message"]
        assert result["output"] == ""


class TestGetNodeResources:
    """Tests for get_node_resources."""

    @patch("tools.kubectl_tools.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        """Parses kubectl top nodes output into structured node metrics."""
        top_output = (
            "NAME           CPU(cores)   CPU%   MEMORY(bytes)   MEMORY%\n"
            "node-1         100m         5%     1000Mi          10%\n"
            "node-2         250m         12%    2048Mi          25%\n"
        )
        mock_run.return_value = _success_result(top_output)

        result = get_node_resources()

        assert result == {
            "error": False,
            "data": [
                {
                    "name": "node-1",
                    "cpu_cores": "100m",
                    "cpu_percent": "5%",
                    "memory_bytes": "1000Mi",
                    "memory_percent": "10%",
                },
                {
                    "name": "node-2",
                    "cpu_cores": "250m",
                    "cpu_percent": "12%",
                    "memory_bytes": "2048Mi",
                    "memory_percent": "25%",
                },
            ],
        }
        mock_run.assert_called_once_with(
            ["kubectl", "top", "nodes"],
            capture_output=True,
            text=True,
            check=True,
        )

    @patch("tools.kubectl_tools.subprocess.run")
    def test_failure(self, mock_run: MagicMock) -> None:
        """Returns structured error when metrics-server is unavailable."""
        mock_run.side_effect = _raise_called_process_error

        result = get_node_resources()

        assert result["error"] is True
        assert result["message"]
        assert result["output"] == ""


class TestGetCrashingPods:
    """Tests for get_crashing_pods."""

    @patch("tools.kubectl_tools.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        """Filters and returns only pods in crashing or unhealthy states."""
        pods_output = (
            "NAMESPACE     NAME              READY   STATUS             RESTARTS   AGE\n"
            "default       bad-pod           0/1     CrashLoopBackOff   5          10m\n"
            "default       healthy-pod       1/1     Running            0          1d\n"
            "kube-system   oom-pod           0/1     OOMKilled          3          2h\n"
            "staging       pending-pod       0/1     Pending            0          5m\n"
        )
        mock_run.return_value = _success_result(pods_output)

        result = get_crashing_pods()

        assert result == {
            "error": False,
            "data": [
                {
                    "namespace": "default",
                    "name": "bad-pod",
                    "ready": "0/1",
                    "status": "CrashLoopBackOff",
                    "restarts": "5",
                    "age": "10m",
                },
                {
                    "namespace": "kube-system",
                    "name": "oom-pod",
                    "ready": "0/1",
                    "status": "OOMKilled",
                    "restarts": "3",
                    "age": "2h",
                },
                {
                    "namespace": "staging",
                    "name": "pending-pod",
                    "ready": "0/1",
                    "status": "Pending",
                    "restarts": "0",
                    "age": "5m",
                },
            ],
        }
        mock_run.assert_called_once_with(
            ["kubectl", "get", "pods", "--all-namespaces"],
            capture_output=True,
            text=True,
            check=True,
        )

    @patch("tools.kubectl_tools.subprocess.run")
    def test_failure(self, mock_run: MagicMock) -> None:
        """Returns structured error when pod listing fails."""
        mock_run.side_effect = _raise_called_process_error

        result = get_crashing_pods()

        assert result["error"] is True
        assert result["message"]
        assert result["output"] == ""
