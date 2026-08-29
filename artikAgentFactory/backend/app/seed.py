"""Idempotent example-agent seeder. Creates agent CONFIGS only by default — never
fabricates Result rows, since presenting invented findings as real would violate this
platform's core rule (every finding must carry a real, live-fetched source). Run with
`--with-runs` to also execute one real live run per seeded agent (costs Anthropic API
calls and takes a few minutes per agent) so the Details page has real data to show.

Usage: python -m app.seed [--with-runs]
"""
from __future__ import annotations

import sys

from app.core.database import SessionLocal, init_db
from app.core.logging_config import log_event, setup_logging
from app.models.agent import Agent
from app.repositories.agent_repo import AgentRepository
from app.schemas.agent import AgentCreate
from app.services.agent_service import AgentService

EXAMPLE_AGENTS = [
    AgentCreate(
        template_id="college_discovery",
        name="AI + Computational Biology Colleges",
        description="Colleges strong in AI-driven drug discovery for an undergraduate applicant.",
        objective="Find colleges that are a strong match for a student interested in AI and computational biology, especially programs touching AI-driven drug discovery.",
        filters={"max_results": 8, "min_relevance": 0.4},
        schedule={"mode": "manual"},
        alert_rules=[{"rule_type": "new_results", "channel": "in_app", "config": {}, "is_enabled": True}],
        status="paused",
    ),
    AgentCreate(
        template_id="stock_news_collector",
        name="Watchlist News",
        description="Material news for a small stock watchlist.",
        objective="Track material news for NVDA, MSFT, and AAPL: earnings, guidance, product announcements, regulatory action.",
        filters={"symbols": "NVDA, MSFT, AAPL", "min_relevance": 0.5, "max_results": 10},
        schedule={"mode": "manual"},
        alert_rules=[{"rule_type": "high_priority_match", "channel": "in_app", "config": {"min_relevance": 0.8}, "is_enabled": True}],
        status="paused",
    ),
    AgentCreate(
        template_id="investment_research",
        name="Renewable Energy Sector Research",
        description="Balanced evidence for and against the renewable-energy sector as an investment theme.",
        objective="Research public evidence for and against investing in the renewable energy sector over a 3-5 year horizon.",
        filters={"subject": "renewable energy sector", "time_horizon": "Medium-term", "max_results": 8},
        schedule={"mode": "manual"},
        alert_rules=[{"rule_type": "changed_results", "channel": "in_app", "config": {}, "is_enabled": True}],
        status="paused",
    ),
    AgentCreate(
        template_id="general_research",
        name="AI Regulation Tracker",
        description="General monitor for meaningful AI regulation developments.",
        objective="Monitor meaningful developments in AI regulation in the US and EU and report significant changes.",
        filters={"max_results": 8},
        schedule={"mode": "manual"},
        alert_rules=[{"rule_type": "run_completed", "channel": "in_app", "config": {}, "is_enabled": True}],
        status="paused",
    ),
]


def seed(with_runs: bool = False) -> None:
    init_db()
    db = SessionLocal()
    try:
        repo = AgentRepository(db)
        if repo.list():
            log_event("app", "seed skipped — agents already exist")
            return

        svc = AgentService(db)
        created: list[Agent] = []
        for draft in EXAMPLE_AGENTS:
            agent = svc.create(draft)
            created.append(agent)
            log_event("app", "seeded agent", id=agent.id, name=agent.name)

        if with_runs:
            from app.services.run_service import execute_run
            for agent in created:
                log_event("app", "seed run starting (live API call)", agent=agent.name)
                run = execute_run(db, agent, trigger="manual")
                log_event("app", "seed run finished", agent=agent.name, status=run.status,
                          results=run.result_count_total)
    finally:
        db.close()


if __name__ == "__main__":
    setup_logging("INFO")
    seed(with_runs="--with-runs" in sys.argv)
