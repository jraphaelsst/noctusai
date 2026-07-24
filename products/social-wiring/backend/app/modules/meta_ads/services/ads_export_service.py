"""Meta Ads report export — per-campaign period aggregation → CSV / PDF.

DB-only (no live Meta calls, so an export can't be rate-limited): sums the
persisted ``ads_insight_snapshots`` per campaign for the window and joins
``ads_objects`` for name/objective/status. Two renderers: CSV (universal,
spreadsheet-friendly) and PDF (a formatted report via reportlab).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

_SCHEMA = "social_wiring"


@dataclass
class CampaignReportRow:
    object_id: str
    name: str
    objective: str
    status: str
    spend_cents: int = 0
    impressions: int = 0
    reach: int = 0
    clicks: int = 0
    leads: float = 0.0

    @property
    def cpl_cents(self) -> int | None:
        return round(self.spend_cents / self.leads) if self.leads else None


@dataclass
class Report:
    account_name: str
    currency: str
    since: str
    until: str
    rows: list[CampaignReportRow] = field(default_factory=list)

    @property
    def total_spend_cents(self) -> int:
        return sum(r.spend_cents for r in self.rows)

    @property
    def total_leads(self) -> float:
        return sum(r.leads for r in self.rows)


def build_report(
    admin: Any, *, org_id: UUID, account_name: str, currency: str,
    since: date, until: date,
) -> Report:
    """Aggregate per-campaign period metrics from the snapshot table +
    campaign metadata from ``ads_objects``. Campaigns with no spend in the
    window are omitted (an empty report row is noise in a spend report)."""
    meta_resp = (
        admin.schema(_SCHEMA).table("ads_objects")
        .select("object_id,name,objective,effective_status")
        .eq("org_id", str(org_id)).eq("level", "campaign")
        .execute()
    )
    meta = {m["object_id"]: m for m in (meta_resp.data or [])}

    snap_resp = (
        admin.schema(_SCHEMA).table("ads_insight_snapshots")
        .select("object_id,spend_cents,impressions,reach,clicks,actions")
        .eq("org_id", str(org_id)).eq("level", "campaign")
        .is_("breakdown_key", "null")
        .gte("date", since.isoformat()).lte("date", until.isoformat())
        .execute()
    )
    by_id: dict[str, CampaignReportRow] = {}
    for s in snap_resp.data or []:
        oid = s["object_id"]
        row = by_id.get(oid)
        if row is None:
            m = meta.get(oid, {})
            row = CampaignReportRow(
                object_id=oid,
                name=m.get("name") or oid,
                objective=(m.get("objective") or "").replace("OUTCOME_", ""),
                status=m.get("effective_status") or "",
            )
            by_id[oid] = row
        row.spend_cents += int(s.get("spend_cents") or 0)
        row.impressions += int(s.get("impressions") or 0)
        row.reach += int(s.get("reach") or 0)
        row.clicks += int(s.get("clicks") or 0)
        actions = s.get("actions") or {}
        try:
            row.leads += float(actions.get("lead", 0.0) or 0.0)
        except (TypeError, ValueError):
            pass

    rows = sorted(by_id.values(), key=lambda r: r.spend_cents, reverse=True)
    return Report(
        account_name=account_name, currency=currency,
        since=since.isoformat(), until=until.isoformat(), rows=rows,
    )


def _reais(cents: int | None) -> str:
    if cents is None:
        return ""
    return f"{cents / 100:.2f}"


# ─── CSV ─────────────────────────────────────────────────────────────────


def to_csv(report: Report) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        f"Relatório de Anúncios — {report.account_name} ({report.currency})",
    ])
    w.writerow([f"Período: {report.since} a {report.until}"])
    w.writerow([])
    w.writerow([
        "Campanha", "Objetivo", "Status",
        f"Gasto ({report.currency})", "Leads",
        f"Custo por lead ({report.currency})",
        "Impressões", "Alcance", "Cliques",
    ])
    for r in report.rows:
        w.writerow([
            r.name, r.objective, r.status,
            _reais(r.spend_cents), f"{r.leads:g}", _reais(r.cpl_cents),
            r.impressions, r.reach, r.clicks,
        ])
    w.writerow([])
    total_cpl = (
        round(report.total_spend_cents / report.total_leads)
        if report.total_leads else None
    )
    w.writerow([
        "TOTAL", "", "", _reais(report.total_spend_cents),
        f"{report.total_leads:g}", _reais(total_cpl), "", "", "",
    ])
    return buf.getvalue()


# ─── PDF ─────────────────────────────────────────────────────────────────


def to_pdf(report: Report) -> bytes:
    """Formatted PDF report via reportlab (declared in requirements.txt)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    story: list[Any] = []
    story.append(Paragraph(
        f"Relatório de Anúncios — {report.account_name}", styles["Title"]))
    story.append(Paragraph(
        f"Período: {report.since} a {report.until} · Moeda: {report.currency}",
        styles["Normal"]))
    total_cpl = (
        report.total_spend_cents / report.total_leads
        if report.total_leads else None
    )
    story.append(Paragraph(
        f"Gasto total: {report.currency} {_reais(report.total_spend_cents)} · "
        f"Leads: {report.total_leads:g} · "
        f"Custo/lead médio: {report.currency} {_reais(round(total_cpl)) if total_cpl else '—'}",
        styles["Normal"]))
    story.append(Spacer(1, 8 * mm))

    header = ["Campanha", "Objetivo", "Status", "Gasto", "Leads",
              "Custo/lead", "Impressões", "Alcance", "Cliques"]
    data = [header] + [
        [
            r.name[:45], r.objective, r.status,
            _reais(r.spend_cents), f"{r.leads:g}", _reais(r.cpl_cents),
            f"{r.impressions:,}", f"{r.reach:,}", f"{r.clicks:,}",
        ]
        for r in report.rows
    ]
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(table)
    doc.build(story)
    return buf.getvalue()
