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
    assert "<title>Check your skin with AI · DermaCareAI</title>" in html
    # theme.js must load before the stylesheet so a saved dark theme applies without a flash
    assert html.index("js/theme.js") < html.index("css/app.css")
    assert 'data-theme-toggle' in html and 'name="color-scheme" content="light dark"' in html
    css = client.get("/static/css/app.css").data.decode()
    assert "tailwindcss" in css, "app.css should be the Tailwind build"
    assert ".dark " in css or ".dark:" in css, "class-based dark mode rules present"
    js = client.get("/static/js/theme.js").data.decode()
    assert 'classList.toggle("dark"' in js and 'saved() || "light"' in js, "light by default; dark only when chosen"


def test_404_page(client):
    r = client.get("/does-not-exist")
    assert r.status_code == 404
    assert b"find that page" in r.data


def test_about_page_without_model_shows_no_fake_metrics(client):
    r = client.get("/about-model")
    assert b"This AI hasn't been trained yet" in r.data
    assert b"Balanced accuracy" not in r.data


def test_about_page_skips_answers_without_measured_results(client, model_dirs):
    """A model answer with no test numbers (e.g. "not a skin problem") must not break the page."""
    from app.extensions import db
    from app.models import ModelVersion
    from tests.conftest import register_model

    register_model(model_dirs["general"])
    mv = db.session.scalar(db.select(ModelVersion).filter_by(domain="general", is_active=True))
    one = {"support": 10, "precision": 0.5, "recall_sensitivity": 0.5, "specificity": 0.9, "f1": 0.5}
    mv.metrics = {"test": {"n_images": 10, "accuracy": 0.5, "balanced_accuracy": 0.5, "macro_f1": 0.5,
                           "per_class": {"eczema": one}}}    # every other answer has no measured results
    db.session.commit()
    r = client.get("/about-model")
    assert r.status_code == 200
    assert b"Balanced accuracy" in r.data or b"50.0%" in r.data
