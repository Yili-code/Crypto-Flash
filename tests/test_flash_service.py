import asyncio
import os
from pathlib import Path
import subprocess
import sys

import pytest

import flash_service as service


@pytest.mark.parametrize("failure", [None, "return", "exception"])
def test_deadline_cleans_up_and_preserves_component_failures(monkeypatch, failure):
    cleaned = []

    async def component():
        try:
            await asyncio.Event().wait()
        finally:
            # Cleanup must be awaited, including asynchronous finalizers.
            await asyncio.sleep(0)
            cleaned.append(True)

    async def fail():
        if failure == "exception":
            raise ValueError("component failed")

    monkeypatch.setattr(service.delivered_flashes, "initialize", lambda: None)
    monkeypatch.setattr(service.jin10_monitor, "main", component)
    monkeypatch.setattr(service.telegram_assistant, "main", component)
    monkeypatch.setattr(service.event_briefing, "main", fail if failure else component)
    if failure:
        error = ValueError if failure == "exception" else RuntimeError
        with pytest.raises(error):
            asyncio.run(service.main(run_seconds=0.02))
    else:
        asyncio.run(service.main(run_seconds=0.02))
    assert len(cleaned) == (2 if failure else 3)


def test_cli_deadline_exits_successfully_without_external_signals():
    # Stub external-service entry points before executing the actual CLI.
    source = """
import asyncio, runpy, sys, types
async def component():
    await asyncio.Event().wait()
for name in ('jin10_monitor', 'telegram_assistant', 'event_briefing'):
    sys.modules[name] = types.SimpleNamespace(main=component)
sys.modules['delivered_flashes'] = types.SimpleNamespace(initialize=lambda: None)
sys.modules['common'] = types.SimpleNamespace(log=types.SimpleNamespace(info=lambda *args: None))
sys.argv = ['flash_service.py', '--run-seconds', '0.02']
runpy.run_path('src/flash_service.py', run_name='__main__')
"""
    result = subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True,
        cwd=Path(__file__).resolve().parents[1], timeout=10,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert result.returncode == 0, result.stderr
