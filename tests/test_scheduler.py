import time
from unittest import TestCase

from billing_collector.collection.scheduler import IntervalScheduler


class IntervalSchedulerTests(TestCase):
    def test_scheduler_runs_job_on_start(self):
        calls: list[int] = []
        scheduler = IntervalScheduler(
            job=lambda: calls.append(1),
            interval_seconds=60,
            run_on_start=True,
        )

        scheduler.start()
        time.sleep(0.01)
        scheduler.stop()

        self.assertEqual(calls, [1])

