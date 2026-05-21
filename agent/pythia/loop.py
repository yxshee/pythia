"""Pythia main loop: Scout -> Analyst -> PM -> Publisher -> Trace.

Run with ``uv run pythia-loop --dry-run`` after ``uv sync``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import click
import structlog
from rich.console import Console
from rich.table import Table

from .analyst import Analyst, AnalystReport
from .config import SETTINGS, Settings
from .fixtures import mock_candidates
from .pm import PortfolioManager, TradePlan
from .publisher import PublishResult, Publisher
from .scout import MarketCandidate, Scout
from .trace import PublishedTrace, TracePublisher


log = structlog.get_logger(__name__)
console = Console()


@dataclass(slots=True)
class CycleReport:
    """One full Scout -> Trace pass, summarized for display + telemetry."""

    candidates: int
    reports: list[AnalystReport]
    plans: list[TradePlan]
    publications: list[PublishResult]
    traces: list[PublishedTrace]


class PythiaLoop:
    """Orchestrates one or more decision cycles."""

    def __init__(self, settings: Settings, use_mock: bool = False):
        self._settings = settings
        self._use_mock = use_mock
        self._analyst = Analyst(settings)
        self._pm = PortfolioManager(settings)
        self._publisher = Publisher(settings)
        self._tracer = TracePublisher(settings)

    async def run_once(self) -> CycleReport:
        if self._use_mock:
            log.info("scout.mock", reason="Polymarket geo-block detected; using fixtures.")
            candidates = mock_candidates()
        else:
            async with Scout(self._settings) as scout:
                candidates = await scout.discover(limit=25)

        reports = [self._analyst.score(c) for c in candidates]
        plans = self._pm.plan(reports)

        publications: list[PublishResult] = []
        traces: list[PublishedTrace] = []

        report_by_market: dict[str, AnalystReport] = {r.market_id: r for r in reports}
        candidate_by_market: dict[str, MarketCandidate] = {c.market_id: c for c in candidates}

        for plan in plans:
            report = report_by_market.get(plan.market_id)
            candidate = candidate_by_market.get(plan.market_id)
            if report is None or candidate is None:
                continue
            # Publish before trace so the trace records the builder-code link.
            publication = self._publisher.publish(plan, candidate)
            publications.append(publication)
            traces.append(self._tracer.publish(report, plan, candidate, publication))

        return CycleReport(
            candidates=len(candidates),
            reports=reports,
            plans=plans,
            publications=publications,
            traces=traces,
        )

    async def run_forever(self, interval_seconds: int = 300) -> None:
        cycle = 1
        while True:
            log.info("loop.cycle_start", cycle=cycle)
            report = await self.run_once()
            _render_cycle(report)
            log.info("loop.cycle_end", cycle=cycle, plans=len(report.plans), traces=len(report.traces))
            cycle += 1
            await asyncio.sleep(interval_seconds)


def _render_cycle(c: CycleReport) -> None:
    title = (
        f"Pythia cycle: {c.candidates} candidates -> {len(c.plans)} plans -> "
        f"{len(c.traces)} traces -> {sum(1 for p in c.publications if p.published)} publications"
    )
    table = Table(title=title)
    table.add_column("market", style="cyan", no_wrap=True)
    table.add_column("decision", style="magenta")
    table.add_column("size USDC", justify="right")
    table.add_column("confidence", justify="right")
    table.add_column("edge bps", justify="right")
    table.add_column("trace", style="dim")
    table.add_column("builder-code link", style="green", overflow="fold")

    trace_by_market = {p.plan.market_id: t for p, t in zip(c.publications, c.traces)}
    publication_by_market = {p.plan.market_id: p for p in c.publications}

    for plan in c.plans:
        trace = trace_by_market.get(plan.market_id)
        publication = publication_by_market.get(plan.market_id)
        table.add_row(
            plan.market_id[:14],
            plan.decision,
            f"${plan.size_usdc:.2f}",
            f"{plan.confidence_bps / 100:.1f}%",
            f"{plan.edge_bps:+d}",
            trace.ipfs_cid[:14] if trace else "-",
            publication.builder_code_link if publication else "-",
        )

    console.print(table)
    if not c.plans:
        console.print("[yellow]No actionable plans this cycle.[/yellow]")


@click.command()
@click.option("--dry-run/--live", default=None, help="Override .env DRY_RUN flag.")
@click.option("--once", is_flag=True, help="Run a single cycle and exit.")
@click.option("--interval", default=300, show_default=True, help="Seconds between cycles when running forever.")
@click.option(
    "--mock/--no-mock",
    default=False,
    help="Use synthetic market fixtures instead of fetching from Polymarket Gamma. "
    "Useful when Polymarket APIs are geo-blocked from the current network.",
)
def main(dry_run: bool | None, once: bool, interval: int, mock: bool) -> None:
    """Run the Pythia decision loop."""
    settings = SETTINGS
    if dry_run is not None:
        settings.pythia_dry_run = dry_run

    structlog.configure(processors=[structlog.dev.ConsoleRenderer()])
    mode_label = "[red]MOCK[/red]" if mock else "[cyan]live[/cyan]"
    console.print(
        f"[bold green]Pythia Builder[/bold green] starting "
        f"mode={mode_label}  "
        f"theme=[cyan]{settings.pythia_theme}[/cyan]  "
        f"builder_code=[yellow]{settings.polymarket_builder_code or 'pythia'}[/yellow]  "
        f"paper_capital=[white]${settings.pythia_paper_capital_usdc:,.0f}[/white]"
    )

    loop = PythiaLoop(settings, use_mock=mock)
    if once:
        asyncio.run(_run_once(loop))
    else:
        asyncio.run(loop.run_forever(interval_seconds=interval))


async def _run_once(loop: PythiaLoop) -> None:
    report = await loop.run_once()
    _render_cycle(report)


if __name__ == "__main__":
    main()
