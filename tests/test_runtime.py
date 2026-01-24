import asyncio
import threading
import time
import unittest
import py_trees
from pydantic import BaseModel

from btflow import ReactiveRunner, StateManager, Status


class SimpleState(BaseModel):
    count: int = 0


class AlwaysRunning(py_trees.behaviour.Behaviour):
    def update(self) -> Status:
        return Status.RUNNING


class WaitForCount(py_trees.behaviour.Behaviour):
    def __init__(self, name: str):
        super().__init__(name)
        self.state_manager = None

    def update(self) -> Status:
        if self.state_manager is None:
            return Status.FAILURE
        return Status.SUCCESS if self.state_manager.get().count >= 1 else Status.RUNNING


class SetupChecksState(py_trees.behaviour.Behaviour):
    def __init__(self, name: str):
        super().__init__(name)
        self.state_manager = None
        self.state_seen_in_setup = None

    def setup(self, **kwargs) -> None:
        self.state_seen_in_setup = self.state_manager is not None

    def update(self) -> Status:
        return Status.SUCCESS


class TestRunnerReuse(unittest.IsolatedAsyncioTestCase):
    async def _run_once(self, runner: ReactiveRunner, state: StateManager):
        state.update({"count": 0})
        runner.tree.interrupt()

        async def trigger():
            await asyncio.sleep(0.05)
            state.update({"count": 1})

        trigger_task = asyncio.create_task(trigger())
        try:
            await asyncio.wait_for(runner.run(max_ticks=10), timeout=1.0)
            return runner.root.status
        finally:
            await trigger_task

    async def test_runner_reuse_wakes_on_state_change(self):
        state = StateManager(SimpleState)
        state.initialize({"count": 0})
        root = WaitForCount("WaitForCount")
        runner = ReactiveRunner(root, state)

        result_first = await self._run_once(runner, state)
        self.assertEqual(result_first, Status.SUCCESS)

        result_second = await self._run_once(runner, state)
        self.assertEqual(result_second, Status.SUCCESS)


class TestRunnerCounters(unittest.IsolatedAsyncioTestCase):
    async def test_max_ticks_counts_across_seconds(self):
        state = StateManager(SimpleState)
        state.initialize({"count": 0})
        root = AlwaysRunning("AlwaysRunning")
        runner = ReactiveRunner(root, state)

        async def ticker():
            while True:
                await asyncio.sleep(0.6)
                state.update({"count": state.get().count + 1})

        ticker_task = asyncio.create_task(ticker())
        try:
            await asyncio.wait_for(runner.run(max_ticks=5, max_fps=100), timeout=5.0)
        finally:
            ticker_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await ticker_task


class TestThreadedWake(unittest.IsolatedAsyncioTestCase):
    async def test_wake_signal_from_other_thread(self):
        state = StateManager(SimpleState)
        state.initialize({"count": 0})
        root = WaitForCount("WaitForCount")
        runner = ReactiveRunner(root, state)

        def trigger():
            time.sleep(0.05)
            state.update({"count": 1})

        thread = threading.Thread(target=trigger)
        thread.start()
        try:
            await asyncio.wait_for(runner.run(max_ticks=10), timeout=1.0)
        finally:
            thread.join()

        self.assertEqual(runner.root.status, Status.SUCCESS)


class TestSetupInjection(unittest.TestCase):
    def test_setup_runs_after_state_injection(self):
        state = StateManager(SimpleState)
        state.initialize({"count": 0})
        root = SetupChecksState("SetupChecksState")
        ReactiveRunner(root, state)
        self.assertTrue(root.state_seen_in_setup)
