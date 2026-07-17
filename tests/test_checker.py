import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from bridge_monitor.models import TargetConfig, TargetType
from bridge_monitor.checker import run_probe


@pytest.mark.asyncio
async def test_probe_http_success():
    target = TargetConfig(
        name="api-health",
        url="http://127.0.0.1:8080/healthz",
        type=TargetType.HTTP,
        expected_status=200,
        timeout_seconds=2.0,
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "OK"

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_resp
        res = await run_probe(target)

        assert res.is_up is True
        assert res.status_code == 200
        assert res.error == ""
        assert res.latency_ms >= 0.0


@pytest.mark.asyncio
async def test_probe_http_expected_string_missing():
    target = TargetConfig(
        name="bridge-worker",
        url="http://127.0.0.1:9000/status",
        type=TargetType.HTTP,
        expected_status=200,
        expected_string="status:ready",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "status:draining"

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_resp
        res = await run_probe(target)

        assert res.is_up is False
        assert "pattern not found" in res.error


@pytest.mark.asyncio
async def test_probe_tcp_success():
    target = TargetConfig(
        name="redis-bridge",
        url="127.0.0.1:6379",
        type=TargetType.TCP,
        timeout_seconds=1.0,
    )

    mock_reader = AsyncMock()
    mock_writer = AsyncMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()

    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_conn:
        mock_conn.return_value = (mock_reader, mock_writer)
        res = await run_probe(target)

        assert res.is_up is True
        assert res.error == ""
        mock_writer.close.assert_called_once()


@pytest.mark.asyncio
async def test_probe_tcp_refused():
    target = TargetConfig(
        name="redis-bridge",
        url="127.0.0.1:6379",
        type=TargetType.TCP,
    )

    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_conn:
        mock_conn.side_effect = ConnectionRefusedError("connection refused")
        res = await run_probe(target)

        assert res.is_up is False
        assert "refused" in res.error.lower()
