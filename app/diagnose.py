"""Diagnose script: run one live fetch per connector and print status."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import List

sys.path.insert(0, ".")

from app.connectors.base import Connector
from app.connectors.remotive import RemotiveConnector
from app.connectors.arbeitnow import ArbeitnowConnector
from app.connectors.remoteok import RemoteOKConnector
from app.connectors.greenhouse import GreenhouseConnector
from app.connectors.lever import LeverConnector
from app.connectors.ashby import AshbyConnector
from app.connectors.adzuna import AdzunaConnector
from app.connectors.jooble import JoobleConnector
from app.connectors.jsearch import JSearchConnector
from app.connectors.remotive import RemotiveConnector
from app.connectors.arbeitnow import ArbeitnowConnector
from app.connectors.remoteok import RemoteOKConnector
from app.connectors.career_crawler import CareerCrawlerConnector
from app.connectors.search_engine import SearchEngineConnector
from app.connectors.alert_email import AlertEmailConnector
from app.connectors.guest_scraper import GuestPageConnector


async def run_connector(name: str, connector) -> dict:
    """Run one fetch and return metrics."""
    print(f"\n{'='*60}")
    print(f"Testing {name}...")
    print(f"{'='*60}")

    result = {
        "name": name,
        "status": "pending",
        "raw_count": 0,
        "saved_count": 0,
        "dropped_count": 0,
        "first_titles": [],
        "exception": None,
    }

    try:
        jobs = await connector.fetch(query="software engineer", location="remote")
        result["raw_count"] = len(jobs)
        result["first_titles"] = [j.title for j in jobs[:2]]
        result["status"] = "ok" if jobs else "zero_results"
        print(f"  raw_count: {result['raw_count']}")
        if result["first_titles"]:
            print(f"  first titles: {result['first_titles']}")
        else:
            print("  ⚠️  Zero results returned")
    except Exception as e:
        result["status"] = "error"
        result["exception"] = str(e)
        print(f"  ❌ ERROR: {e}")

    return result


async def main():
    print("Starting connector diagnosis...")

    connectors = [
        ("remotive", RemotiveConnector()),
        ("arbeitnow", ArbeitnowConnector()),
        ("remoteok", RemoteOKConnector()),
        ("greenhouse", GreenhouseConnector()),
        ("lever", LeverConnector()),
        ("ashby", AshbyConnector(board_name="test")),
        ("search_engine", SearchEngineConnector()),
        ("career_crawler", CareerCrawlerConnector()),
        ("alert_email", AlertEmailConnector()),
        ("guest_scraper", GuestPageConnector(enabled=False)),
    ]

    results = []
    for name, connector in connectors:
        result = await run_connector(name, connector)
        results.append(result)

        # Close client connections
        if hasattr(connector, 'client') and connector.client:
            await connector.client.aclose()

    # Summary
    print("\n" + "="*70)
    print("DIAGNOSIS SUMMARY")
    print("="*70)

    ok = sum(1 for r in results if r["status"] == "ok")
    zero = sum(1 for r in results if r["status"] == "zero_results")
    err = sum(1 for r in results if r["status"] == "error")

    print(f"Total: {len(results)} | OK: {ok} | Zero results: {zero} | Errors: {err}")

    for r in results:
        status_icon = "✅" if r["status"] == "ok" else ("⚠️" if r["status"] == "zero_results" else "❌")
        print(f"  {status_icon} {r['name']}: {r['status']} (raw={r['raw_count']})")
        if r["exception"]:
            print(f"    Exception: {r['exception']}")

    # Exit code
    if err > 0:
        sys.exit(1)
    elif zero == len(results):
        sys.exit(2)


if __name__ == "__main__":
    import sys
    asyncio.run(main())