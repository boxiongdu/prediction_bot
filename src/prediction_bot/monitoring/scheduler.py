"""
Report scheduler — generates reports on a schedule.

Read-only. Uses the Reporter for content generation and AlertManager
for delivery. Never affects trade execution.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from prediction_bot.monitoring.alerts import AlertManager
from prediction_bot.monitoring.reporter import Reporter

logger = logging.getLogger(__name__)


class ReportScheduler:
    """Generates and delivers reports on a schedule.

    Usage:
        sched = ReportScheduler()
        sched.run_once()           # generate + print daily
        sched.run_loop(interval_hours=24)   # loop forever
    """

    def __init__(
        self,
        reporter: Reporter | None = None,
        alerts: AlertManager | None = None,
    ) -> None:
        self._reporter = reporter or Reporter()
        self._alerts = alerts or AlertManager()
        self._last_daily: str = ""
        self._last_weekly: str = ""

    def run_once(self) -> None:
        """Generate and print both reports."""
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")

        # Daily report
        if self._last_daily != today:
            report = self._reporter.generate_daily()
            self._last_daily = today
            print(report)
            logger.info("Daily report generated for %s", today)

        # Weekly report (Mondays)
        if now.weekday() == 0 and self._last_weekly != today:
            report = self._reporter.generate_weekly()
            self._last_weekly = today
            print(report)
            logger.info("Weekly report generated for %s", today)

    def run_loop(self, interval_hours: int = 24) -> None:
        """Run report generation loop forever."""
        logger.info(
            "Report scheduler starting (interval=%dh)", interval_hours,
        )
        while True:
            try:
                self.run_once()
            except Exception as e:
                logger.error("Report generation failed: %s", e)
            time.sleep(interval_hours * 3600)

    def send_daily_alert(self) -> None:
        """Generate daily report and send via alert channel."""
        report = self._reporter.generate_daily()
        self._alerts.send({
            "type": "daily_report",
            "report": report,
        })


def print_reports() -> None:
    """Quick report generation for CLI or cron."""
    reporter = Reporter()
    reporter.print_daily()
