from __future__ import annotations

import logging
import threading
from collections.abc import Callable

LOGGER = logging.getLogger(__name__)


class IntervalScheduler:
    def __init__(
        self,
        *,
        job: Callable[[], None],
        interval_seconds: int,
        run_on_start: bool = True,
    ) -> None:
        self.job = job
        self.interval_seconds = interval_seconds
        self.run_on_start = run_on_start
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="billing-collector", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    def _run(self) -> None:
        if self.run_on_start:
            self._run_once()
        while not self._stop.wait(self.interval_seconds):
            self._run_once()

    def _run_once(self) -> None:
        try:
            self.job()
        except Exception:
            LOGGER.exception("scheduled billing collection failed")
