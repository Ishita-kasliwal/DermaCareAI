def test_health_root(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_health_api(client):
    assert client.get("/api/v1/health").status_code == 200


def test_public_pages_render(client):
    for path in ("/", "/about-model", "/auth/login", "/auth/register"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert b"cannot give a diagnosis" in r.data


def test_brand_and_theme_assets(client, app):
    html = client.get("/").data.decode()
    assert app.config["BRAND_NAME"] == "DermaCareAI"
    assert "<title>Check a skin spot with AI · DermaCareAI</title>" in html
    # theme.js must load before the stylesheet so a saved dark theme applies without a flash
    assert html.index("js/theme.js") < html.index("css/app.css")
    assert 'data-theme-toggle' in html and 'name="color-scheme" content="light dark"' in html
    css = client.get("/static/css/app.css").data.decode()
    assert "@media (prefers-color-scheme: dark)" in css and ':root[data-theme="dark"]' in css
    assert client.get("/static/js/theme.js").status_code == 200


def test_404_page(client):
    r = client.get("/does-not-exist")
    assert r.status_code == 404
    assert b"find that page" in r.data


def test_about_page_without_model_shows_no_fake_metrics(client):
    r = client.get("/about-model")
    assert b"The AI hasn't been trained yet" in r.data
    assert b"Balanced accuracy" not in r.data
