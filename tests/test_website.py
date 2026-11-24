import re

import pytest

from bid_studio.catalog import SERVICES

SITE = ["/", "/services", "/pricing", "/about", "/contact", "/developers"]


@pytest.mark.parametrize("path", SITE)
def test_marketing_pages_render_with_shared_layout(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert 'href="/services"' in r.text and 'href="/app"' in r.text  # header nav
    assert "<title>" in r.text and "site.css" in r.text


@pytest.mark.parametrize("service", SERVICES, ids=lambda s: s.slug)
def test_every_service_has_a_detail_page_and_app_page(client, service):
    page = client.get(f"/services/{service.slug}")
    assert page.status_code == 200
    assert service.title.replace("&", "&amp;") in page.text
    assert f"/app/{service.slug}" in page.text
    app_page = client.get(f"/app/{service.slug}")
    assert app_page.status_code == 200
    # nav marks exactly this page active
    assert re.search(rf'href="/app/{service.slug}[^"]*" class="active"', app_page.text)


def test_app_sections_declare_the_data_they_need(client):
    html = client.get("/app/grants").text
    assert '["grants", "proposals"]' in html or '["grants","proposals"]' in html
    assert "/static/app.js" in html


def test_workspace_param_is_kept_in_app_links(client):
    html = client.get("/app/grants?workspace_id=1").text
    assert "/app/pricing?workspace_id=1" in html


def test_unknown_service_and_app_page_404(client):
    assert client.get("/services/nope").status_code == 404
    assert client.get("/app/nope").status_code == 404


def test_html_404_is_branded_but_api_404_is_json(client):
    page = client.get("/definitely-not-here", headers={"Accept": "text/html"})
    assert page.status_code == 404 and "find that page" in page.text
    api = client.get("/api/v1/nothing", headers={"Accept": "text/html"})
    assert api.status_code == 404 and api.json()["detail"]


def test_static_assets_and_seo_files(client):
    assert client.get("/static/site.css").status_code == 200
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/robots.txt").text.startswith("User-agent")
    sm = client.get("/sitemap.xml")
    assert sm.status_code == 200 and "/services/grants" in sm.text and "/app/" not in sm.text


def test_contact_page_does_not_pretend_to_store_messages(client):
    assert "mailto:" in client.get("/contact").text


def test_markdown_export_preview_uses_a_real_element_lookup(client):
    """E() returns a sink object when an element is missing, so it must never be used to
    decide whether the export preview already exists (that silently hid every export)."""
    js = client.get("/static/app.js").text
    assert 'let wrap = document.getElementById(previewId)' in js
