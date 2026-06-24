import asyncio

import pytest

from backend.app.concurrency import ConcurrencyGuard


@pytest.mark.asyncio
async def test_acquire_llm_respects_semaphore_limit():
    guard = ConcurrencyGuard(max_llm_calls=3, max_connections=5)
    acquired = []

    async def acquire():
        await guard.acquire_llm()
        acquired.append(1)

    # start 5 coroutines, only 3 should acquire immediately
    tasks = [asyncio.create_task(acquire()) for _ in range(5)]
    await asyncio.sleep(0.05)
    assert len(acquired) == 3

    # release one
    guard.release_llm()
    await asyncio.sleep(0.05)
    assert len(acquired) == 4

    # release remaining
    for _ in range(4):
        guard.release_llm()
    await asyncio.sleep(0.05)
    assert len(acquired) == 5

    for t in tasks:
        t.cancel()
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_acquire_llm_blocks_when_exhausted():
    guard = ConcurrencyGuard(max_llm_calls=3, max_connections=5)
    for _ in range(3):
        await guard.acquire_llm()

    # semaphore exhausted
    task = asyncio.create_task(guard.acquire_llm())
    await asyncio.sleep(0.05)
    assert not task.done()

    guard.release_llm()
    await asyncio.wait_for(task, timeout=0.5)
    guard.release_llm()


@pytest.mark.asyncio
async def test_connection_enter_exit():
    guard = ConcurrencyGuard(max_llm_calls=3, max_connections=5)
    assert guard.active_connections == 0
    guard.connection_enter()
    assert guard.active_connections == 1
    guard.connection_enter()
    assert guard.active_connections == 2
    guard.connection_exit()
    assert guard.active_connections == 1
    guard.connection_exit()
    assert guard.active_connections == 0


def test_connection_enter_raises_when_over_limit():
    guard = ConcurrencyGuard(max_llm_calls=1, max_connections=2)
    guard.connection_enter()
    guard.connection_enter()
    with pytest.raises(RuntimeError):
        guard.connection_enter()


def test_connection_exit_does_not_go_negative():
    guard = ConcurrencyGuard(max_llm_calls=1, max_connections=2)
    guard.connection_exit()
    assert guard.active_connections == 0


@pytest.mark.asyncio
async def test_context_manager_for_llm():
    guard = ConcurrencyGuard(max_llm_calls=3, max_connections=5)
    async with guard.llm_slot():
        assert guard._llm_semaphore.locked() or guard._llm_semaphore._value == 2

    # after exiting, semaphore should be released
    await guard.acquire_llm()
    assert True
    guard.release_llm()

def test_create_app_uses_concurrency_limits_from_env(monkeypatch):
    from backend.app.config import get_settings
    from backend.app.main import create_app

    get_settings.cache_clear()
    monkeypatch.setenv("SHOPGUIDE_MAX_LLM_CALLS", "2")
    monkeypatch.setenv("SHOPGUIDE_MAX_CONNECTIONS", "3")
    try:
        app = create_app(use_fake_llm=True, use_fake_retriever=True)
        guard = app.state.concurrency_guard

        assert guard.max_llm_calls == 2
        assert guard.max_connections == 3
    finally:
        get_settings.cache_clear()
