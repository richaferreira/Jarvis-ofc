"""Native jobs must retain capacity after their awaiting coroutine is cancelled."""

import asyncio
import threading
import unittest

from app.infrastructure.worker import BlockingWorker


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_native_job_does_not_release_capacity_early(self):
        worker = BlockingWorker("test")
        started, finish = threading.Event(), threading.Event()

        def blocking():
            started.set()
            finish.wait(2)
            return 1

        first = asyncio.create_task(worker.run(blocking))
        await asyncio.to_thread(started.wait, 1)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(worker.run(lambda: 2))
        await asyncio.sleep(0.02)
        self.assertFalse(second.done())
        finish.set()
        self.assertEqual(await second, 2)
        await worker.aclose()

    async def test_worker_recovers_after_native_exception(self):
        worker = BlockingWorker("test-errors")
        with self.assertRaises(ZeroDivisionError):
            await worker.run(lambda: 1 / 0)
        self.assertEqual(await worker.run(lambda: 42), 42)
        await worker.aclose()
        with self.assertRaises(RuntimeError):
            await worker.run(lambda: 1)
