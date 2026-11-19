def test_win_loss_debrief_generates_letter_and_fixes(client):
    res = client.post(
        "/api/v1/debriefs/compare",
        json={
            "workspace_id": 1,
            "bid_title": "Regional Cloud Migration",
            "buyer_name": "Yorkshire Council",
            "outcome": "lost",
            "contract_value": 520000,
            "criterion_comparisons": [
                {"criterion": "Security Architecture", "internal_score": 90, "buyer_score": 68},
                {"criterion": "Price", "internal_score": 75, "buyer_score": 76},
            ],
            "send_feedback_request": True,
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["internal_score"] == 82.5
    assert body["buyer_score"] == 72.0
    assert "Yorkshire Council" in body["feedback_request_letter"]
    assert len(body["next_bid_fixes"]) == 1
    assert body["next_bid_fixes"][0]["criterion"] == "Security Architecture"

    export_res = client.get(f"/api/v1/debriefs/outcomes/{body['id']}/export")
    assert export_res.status_code == 200
    assert "Regional Cloud Migration" in export_res.json()["markdown"]


def test_clarification_pack_reader_surfaces_ambiguities_and_tracks_answers(client):
    res = client.post(
        "/api/v1/clarifications/analyze-pack",
        json={
            "workspace_id": 1,
            "tender_title": "Riverbend Fleet Support",
            "clarification_deadline": "2026-12-01",
            "source_text": (
                "The contractor shall maintain reasonable response times. "
                "Telemetry hardware, spares, etc. must be supplied at no cost. "
                "Start date is TBD."
            ),
        },
    )
    assert res.status_code == 201
    pack = res.json()
    assert len(pack["questions"]) >= 3

    first_qid = pack["questions"][0]["id"]
    upd = client.patch(
        f"/api/v1/clarifications/{pack['id']}/questions",
        json={
            "question_id": first_qid,
            "status": "answered",
            "buyer_response": "Response time SLA is confirmed as 4 business hours.",
        },
    )
    assert upd.status_code == 200
    assert upd.json()["questions"][0]["status"] == "answered"

    export_res = client.get(f"/api/v1/clarifications/{pack['id']}/export")
    assert export_res.status_code == 200
    assert "Clarification Register" in export_res.json()["markdown"]


def test_pricing_matrix_calculation_and_narrative(client):
    templates = client.get("/api/v1/pricing/templates").json()
    assert len(templates) >= 2

    res = client.post(
        "/api/v1/pricing/matrices",
        json={
            "workspace_id": 1,
            "bid_title": "Riverbend Fleet Software",
            "template_id": templates[0]["id"],
            "currency": "GBP",
            "margin_pct": 15.0,
            "contingency_pct": 5.0,
            "lines": [
                {"category": "Mobilisation", "description": "Setup", "unit": "day", "quantity": 10, "unit_rate": 500},
                {"category": "Delivery", "description": "Engineering", "unit": "day", "quantity": 20, "unit_rate": 750},
            ],
        },
    )
    assert res.status_code == 201
    matrix = res.json()
    assert matrix["subtotal"] == 20000.0
    assert matrix["total_price"] == 24000.0
    assert "GBP 24,000.00" in matrix["cost_narrative"]

    # Creating a matrix from a template ID without custom lines loads template defaults
    tpl_res = client.post(
        "/api/v1/pricing/matrices",
        json={
            "workspace_id": 1,
            "bid_title": "Template-Seeded Bid",
            "template_id": templates[0]["id"],
            "currency": "GBP",
        },
    )
    assert tpl_res.status_code == 201
    assert tpl_res.json()["subtotal"] > 0
    assert tpl_res.json()["margin_pct"] == templates[0]["default_margin_pct"]

    export_res = client.get(f"/api/v1/pricing/matrices/{matrix['id']}/export")
    assert export_res.status_code == 200
    assert "Evaluator Cost Narrative" in export_res.json()["markdown"]


def test_social_value_net_zero_and_living_wage_statement(client):
    res = client.post(
        "/api/v1/social-value",
        json={
            "workspace_id": 1,
            "bid_title": "Riverbend Electric Refuse Contract",
            "buyer_framework": "UK_PPN_06_20",
            "themes": ["Fighting Climate Change", "Tackling Economic Inequality"],
            "net_zero_target_year": 2032,
            "baseline_emissions_tco2e": 150.0,
            "annual_reduction_pct": 10.0,
            "real_living_wage_accredited": True,
        },
    )
    assert res.status_code == 201
    sv = res.json()
    assert "Net Zero by 2032" in sv["generated_statement"]
    assert "Real Living Wage" in sv["generated_statement"]
    assert len(sv["kpis"]) >= 3

    export_res = client.get(f"/api/v1/social-value/{sv['id']}/export")
    assert export_res.status_code == 200
    assert "| KPI | Target |" in export_res.json()["markdown"]
