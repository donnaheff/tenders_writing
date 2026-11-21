import pytest


@pytest.mark.parametrize(
    "path,text",
    [
        ("/", "grant and funding applications"),
        ("/grants", "Open grants"),
        ("/writers", "Grant writers"),
        ("/market", "Writers marketplace"),
        ("/features", "Grant &amp; funding proposals"),
        ("/pricing", "Consultancy"),
        ("/about", "About Bid Studio"),
        ("/contact", "Send message"),
    ],
)
def test_public_pages_render(client, path, text):
    res = client.get(path)
    assert res.status_code == 200
    assert text in res.text
    assert 'href="/app"' in res.text


def test_dashboard_moved_to_app(client):
    res = client.get("/app")
    assert res.status_code == 200
    assert "apiNotices" in res.text


def test_static_css_served(client):
    res = client.get("/static/site.css")
    assert res.status_code == 200
    assert "text/css" in res.headers["content-type"]


def test_contact_request_saved_and_validated(client):
    ok = client.post(
        "/api/v1/contact",
        json={"name": "Sam", "email": "sam@example.org", "plan": "team", "message": "Hello"},
    )
    assert ok.status_code == 201
    assert ok.json()["status"] == "received"

    bad = client.post(
        "/api/v1/contact",
        json={"name": "Sam", "email": "not-an-email", "message": "Hello"},
    )
    assert bad.status_code == 422


def test_writer_profile_page_renders(client):
    page = client.get("/writers/7")
    assert page.status_code == 200 and "const WID = 7" in page.text
    assert client.get("/writers/abc").status_code == 422
