"""Bounded bridge for blocking libraries; cancellation cannot grow the thread queue."""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")


class BlockingWorker:
    """One in-flight native job, including jobs whose awaiter timed out."""

    def __init__(self, name: str) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=name)
        self._slot = asyncio.Semaphore(1)
        self._closed = False

    async def run(self, function: Callable[..., T], *args: object) -> T:
        """Wait for capacity and shield native execution while preserving cancellation."""
        await self._slot.acquire()
        if self._closed:
            self._slot.release()
            raise RuntimeError("Worker encerrado.")
        try:
            future = asyncio.get_running_loop().run_in_executor(self._executor, function, *args)
        except BaseException:
            self._slot.release()
            raise

        def release(done: asyncio.Future[T]) -> None:
            self._slot.release()
            if not done.cancelled():
                done.exception()  # Retrieve exceptions even if the original awaiter left.

        future.add_done_callback(release)
        return await asyncio.shield(future)

    async def aclose(self) -> None:
        """Drain the bounded worker without blocking the event loop."""
        self._closed = True
        await asyncio.to_thread(self._executor.shutdown, wait=True, cancel_futures=True)
