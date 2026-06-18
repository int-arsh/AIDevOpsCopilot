"""Unit tests for prometheus_tools with mocked httpx.AsyncClient calls."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tools.prometheus_tools import get_anomalies, query_prometheus


def _mock_http_response(payload: dict, status_code: int = 200) -> MagicMock:
    """Build a mock httpx response that returns the given JSON payload."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    return response


def _configure_async_client(
    mock_async_client: MagicMock,
    get_return_value: MagicMock | None = None,
    get_side_effect: Exception | None = None,
) -> AsyncMock:
    """Wire httpx.AsyncClient context manager to return a mocked client."""
    mock_client = AsyncMock()
    if get_side_effect is not None:
        mock_client.get = AsyncMock(side_effect=get_side_effect)
    else:
        mock_client.get = AsyncMock(return_value=get_return_value)

    mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_client


def _vector_result(
    metric: dict[str, str],
    value: str,
    timestamp: int = 1718719200,
) -> dict:
    """Build a single Prometheus instant-query vector result entry."""
    return {"metric": metric, "value": [timestamp, value]}


def _success_payload(results: list[dict]) -> dict:
    """Build a Prometheus API success response body."""
    return {
        "status": "success",
        "data": {"resultType": "vector", "result": results},
    }


class TestQueryPrometheus:
    """Tests for query_prometheus."""

    @pytest.mark.asyncio
    @patch("tools.prometheus_tools.httpx.AsyncClient")
    async def test_successful_response(
        self, mock_async_client: MagicMock
    ) -> None:
        """Returns parsed JSON when Prometheus responds with 200."""
        payload = _success_payload(
            [
                _vector_result(
                    {"container": "app", "pod": "web-1", "namespace": "default"},
                    "0.42",
                )
            ]
        )
        mock_client = _configure_async_client(
            mock_async_client, get_return_value=_mock_http_response(payload)
        )

        result = await query_prometheus("up")

        assert result == {"error": False, "data": payload}
        mock_client.get.assert_awaited_once_with(
            "http://localhost:9090/api/v1/query",
            params={"query": "up"},
        )

    @pytest.mark.asyncio
    @patch("tools.prometheus_tools.httpx.AsyncClient")
    async def test_connection_error(self, mock_async_client: MagicMock) -> None:
        """Returns structured error when the HTTP client cannot connect."""
        _configure_async_client(
            mock_async_client,
            get_side_effect=httpx.ConnectError("All connection attempts failed"),
        )

        result = await query_prometheus("up")

        assert result["error"] is True
        assert "All connection attempts failed" in result["message"]

    @pytest.mark.asyncio
    @patch("tools.prometheus_tools.httpx.AsyncClient")
    async def test_timeout_error(self, mock_async_client: MagicMock) -> None:
        """Returns structured error when the HTTP request times out."""
        _configure_async_client(
            mock_async_client,
            get_side_effect=httpx.TimeoutException("Request timed out"),
        )

        result = await query_prometheus("up")

        assert result["error"] is True
        assert "Request timed out" in result["message"]


class TestGetAnomalies:
    """End-to-end tests for get_anomalies with mocked Prometheus responses."""

    @pytest.mark.asyncio
    @patch("tools.prometheus_tools.httpx.AsyncClient")
    async def test_end_to_end_with_mocked_data(
        self, mock_async_client: MagicMock
    ) -> None:
        """Combines CPU, memory, and restart anomaly results from mocked queries."""
        cpu_payload = _success_payload(
            [
                _vector_result(
                    {
                        "container": "worker",
                        "pod": "api-1",
                        "namespace": "prod",
                    },
                    "0.10",
                ),
                _vector_result(
                    {
                        "container": "sidecar",
                        "pod": "api-1",
                        "namespace": "prod",
                    },
                    "0.95",
                ),
                _vector_result(
                    {
                        "container": "app",
                        "pod": "web-2",
                        "namespace": "staging",
                    },
                    "0.50",
                ),
            ]
        )
        memory_payload = _success_payload(
            [
                _vector_result(
                    {
                        "container": "app",
                        "pod": "web-1",
                        "namespace": "default",
                    },
                    "0.85",
                ),
                _vector_result(
                    {
                        "container": "cache",
                        "pod": "redis-0",
                        "namespace": "default",
                    },
                    "0.50",
                ),
            ]
        )
        restart_payload = _success_payload(
            [
                _vector_result(
                    {
                        "container": "app",
                        "pod": "crash-loop",
                        "namespace": "prod",
                    },
                    "5",
                ),
                _vector_result(
                    {
                        "container": "app",
                        "pod": "stable",
                        "namespace": "prod",
                    },
                    "1",
                ),
            ]
        )

        async def mock_get(_url: str, params: dict | None = None) -> MagicMock:
            """Return a different Prometheus payload based on the PromQL query."""
            query = (params or {}).get("query", "")
            if "container_cpu_usage_seconds_total" in query:
                return _mock_http_response(cpu_payload)
            if "container_memory_usage_bytes" in query:
                return _mock_http_response(memory_payload)
            if "kube_pod_container_status_restarts_total" in query:
                return _mock_http_response(restart_payload)
            raise AssertionError(f"Unexpected PromQL query: {query}")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=mock_get)
        mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await get_anomalies()

        assert result == {
            "error": False,
            "data": {
                "cpu": {
                    "error": False,
                    "data": [
                        {
                            "container": "sidecar",
                            "pod": "api-1",
                            "namespace": "prod",
                            "cpu_rate": 0.95,
                        },
                        {
                            "container": "app",
                            "pod": "web-2",
                            "namespace": "staging",
                            "cpu_rate": 0.50,
                        },
                        {
                            "container": "worker",
                            "pod": "api-1",
                            "namespace": "prod",
                            "cpu_rate": 0.10,
                        },
                    ],
                },
                "memory": {
                    "error": False,
                    "data": [
                        {
                            "container": "app",
                            "pod": "web-1",
                            "namespace": "default",
                            "memory_ratio": 0.85,
                            "memory_percent": 85.0,
                        },
                    ],
                },
                "restarts": {
                    "error": False,
                    "data": [
                        {
                            "container": "app",
                            "pod": "crash-loop",
                            "namespace": "prod",
                            "restarts_last_hour": 5.0,
                        },
                    ],
                },
            },
        }
        assert mock_client.get.await_count == 3
