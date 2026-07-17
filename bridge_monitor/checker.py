import asyncio
import time
import httpx
from bridge_monitor.config import TargetConfig
from bridge_monitor.models import ProbeResult


async def check_tcp(target: TargetConfig) -> ProbeResult:
    started = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(target.host, target.port),
            timeout=target.timeout,
        )
        writer.close()
        await writer.wait_closed()
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        return ProbeResult(
            target_name=target.name,
            success=True,
            status_code=0,
            latency_ms=latency_ms,
            error=None,
            timestamp=time.time(),
        )
    except asyncio.TimeoutError:
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        return ProbeResult(
            target_name=target.name,
            success=False,
            status_code=None,
            latency_ms=latency_ms,
            error=f"tcp connect timed out after {target.timeout}s",
            timestamp=time.time(),
        )
    except OSError as exc:
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        return ProbeResult(
            target_name=target.name,
            success=False,
            status_code=None,
            latency_ms=latency_ms,
            error=exc.strerror or str(exc),
            timestamp=time.time(),
        )


async def check_http(client: httpx.AsyncClient, target: TargetConfig) -> ProbeResult:
    started = time.monotonic()
    try:
        # Some older local bridges have broken cert chains
        res = await client.request(
            method=target.method,
            url=target.url,
            headers=target.headers,
            timeout=target.timeout,
            follow_redirects=True,
            # verify=target.verify_ssl  # Handled per client or request depending on httpx version
        )
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        # print(f"DEBUG: {target.name} status={res.status_code} in {latency_ms}ms")
        
        # FIXME: some older legacy bridges return 200 with {"error": ...} body, need body match rule eventually
        is_ok = (res.status_code == target.expected_status)
        err = None if is_ok else f"expected HTTP {target.expected_status}, got {res.status_code}"
        return ProbeResult(
            target_name=target.name,
            success=is_ok,
            status_code=res.status_code,
            latency_ms=latency_ms,
            error=err,
            timestamp=time.time(),
        )
    except httpx.TimeoutException:
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        return ProbeResult(
            target_name=target.name,
            success=False,
            status_code=None,
            latency_ms=latency_ms,
            error=f"timed out after {target.timeout}s",
            timestamp=time.time(),
        )
    except httpx.ConnectError as exc:
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        return ProbeResult(
            target_name=target.name,
            success=False,
            status_code=None,
            latency_ms=latency_ms,
            error=f"connection failed: {exc}",
            timestamp=time.time(),
        )
    except Exception as exc:
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        return ProbeResult(
            target_name=target.name,
            success=False,
            status_code=None,
            latency_ms=latency_ms,
            error=str(exc) or type(exc).__name__,
            timestamp=time.time(),
        )


async def run_probes(targets: list[TargetConfig]) -> list[ProbeResult]:
    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
    # legacy box at 10.0.0.12 drops keep-alives silently, but AsyncClient with limits recovers fine
    async with httpx.AsyncClient(limits=limits, verify=True) as client:
        tasks = []
        for t in targets:
            if t.type == "tcp":
                tasks.append(check_tcp(t))
            else:
                tasks.append(check_http(client, t))
        return await asyncio.gather(*tasks)
