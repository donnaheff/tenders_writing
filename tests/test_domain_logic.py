import importlib.util
from pathlib import Path
from types import SimpleNamespace

from bid_studio.database import normalize_database_url
from bid_studio.services.domain_logic import (
    analyze_pack_for_clarifications,
    build_buyer_intelligence_report,
    calculate_price_matrix,
    compute_proposal_weighted_score,
    extract_grant_criteria,
    validate_public_sector_draft,
)


def test_compute_proposal_weighted_score_edge_cases():
    assert compute_proposal_weighted_score([]) == 0.0
    assert compute_proposal_weighted_score([{"weight": 0, "max_score": 5, "self_score": 5}]) == 0.0
    # Clamps self_score above max_score and below 0
    score = compute_proposal_weighted_score(
        [
            {"weight": 50, "max_score": 5, "self_score": 8},
            {"weight": 50, "max_score": 5, "self_score": -2},
        ]
    )
    assert score == 50.0


def test_extract_grant_criteria_from_text_and_presets():
    from_text = extract_grant_criteria(
        [],
        "Grant: Excellence (50%); Impact (30%); Governance (20%)",
        "Foundation",
    )
    assert len(from_text) == 3
    assert sum(c["weight"] for c in from_text) == 100.0

    preset = extract_grant_criteria([], "No explicit weights listed here.", "World Bank")
    assert len(preset) == 3
    assert preset[0]["max_score"] == 100.0


def test_calculate_price_matrix_and_buyer_intel_empty():
    lines, subtotal, total = calculate_price_matrix(
        [{"category": "Ops", "description": "Support", "quantity": 4, "unit_rate": 250}],
        margin_pct=20.0,
        contingency_pct=10.0,
    )
    assert subtotal == 1000.0
    assert total == 1300.0
    assert lines[0]["line_id"] == "L1"

    empty_intel = build_buyer_intelligence_report("Unknown Council", None, [])
    assert empty_intel["awards_analyzed"] == 0
    assert empty_intel["top_winners"] == []


def test_clarifications_fallback_and_public_sector_validation_edges():
    qs = analyze_pack_for_clarifications(
        "The supplier shall install 10 servers by 1 March 2027 with 99.9% uptime."
    )
    assert len(qs) == 1
    assert qs[0]["priority"] == "Low"
    assert "TUPE" in qs[0]["drafted_question"]

    clarity, issues, status = validate_public_sector_draft(
        "Short spec",
        [{"name": "Quality", "weight_pct": 100, "max_score": 0, "scoring_guidance": ""}],
    )
    assert status == "draft"
    assert clarity < 100.0
    assert len(issues) == 3

    notice = SimpleNamespace(
        notice_type="awarded_tender",
        funder_or_buyer="Riverbend",
        sector="IT",
        contract_value=100000.0,
        awarded_supplier="Acme Ltd",
    )
    intel = build_buyer_intelligence_report("Riverbend", "IT", [notice])
    assert intel["awards_analyzed"] == 1
    assert intel["top_winners"][0]["share_pct"] == 100.0


def test_normalize_database_url_and_vercel_entrypoint(monkeypatch):
    api_path = Path(__file__).resolve().parent.parent / "api" / "index.py"
    spec = importlib.util.spec_from_file_location("vercel_api_index", api_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.app.title == "Bid Studio"

    assert (
        normalize_database_url("postgres://user:pass@db.example:5432/app")
        == "postgresql://user:pass@db.example:5432/app"
    )
    monkeypatch.setenv("VERCEL", "1")
    assert normalize_database_url("sqlite:///./bid_studio.db") == "sqlite:////tmp/bid_studio.db"
    monkeypatch.delenv("VERCEL", raising=False)
    assert normalize_database_url("sqlite:///./bid_studio.db") == "sqlite:///./bid_studio.db"
