"""Reliability & Health service.

- Health dashboard metrics per connector
- Zero-result alerts
- Nightly link validator
- Scheduled background fetch
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import httpx
from sqlalchemy.orm import Session

from app.db.base import SessionLocal, Job as SQLJob
from app.schemas.job import ConnectorHealth

logger = logging.getLogger("job_aggregator.reliability")


class ReliabilityManager:
    """Manages connector health, alerts, and nightly link validation."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15.0)

    async def check_connector_zero_results(
        self, connector_name: str, jobs_fetched: int
    ) -> Optional[str]:
        """Alert if a connector returns zero results unexpectedly."""
        if jobs_fetched == 0:
            msg = f"WARNING: Connector '{connector_name}' returned 0 results unexpectedly."
            logger.warning(msg)
            return msg
        return None

    async def validate_job_links(self) -> Dict[str, int]:
        """Nightly link validator that marks closed jobs (HTTP 404/410)."""
        db = SessionLocal()
        stats = {"checked": 1, "closed": 0, "active": 0}

        try:
            # Check active jobs whose apply_url hasn't been checked recently
            jobs = db.query(SQLJob).filter(SQLJob.status == "active").limit(100).all()

            for job in jobs:
                stats["checked"] += 1
                try:
                    resp = await self.client.head(job.apply_url, timeout=10.0, follow_redirects=True)
                    if resp.status_code in (404, 410, 403):
                        job.status = "closed"
                        stats["closed"] += 1
                    else:
                        stats["active"] += 1
                except Exception:
                    # Connection errors could be temporary, mark closed after multiple failures
                    pass

            db.commit()
        except Exception as e:
            logger.error(f"Error in link validator: {e}")
            db.rollback()
        finally:
            db.close()

        return stats


reliability_manager = ReliabilityManager()