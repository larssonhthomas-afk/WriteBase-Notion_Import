import pytest
from fastapi.testclient import TestClient
from PIL import Image

from server.app import create_app, matches
from server.config import ConfigError, Settings, load_settings
from server.framebuffer import BUFFER_SIZE, PANEL_HEIGHT, PANEL_WIDTH

TOKEN = "t" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class StubRenderer:
    """Hoppar över Chromium. Autentisering och ETag beror inte på bildinnehållet."""

    def __init__(self) -> None:
        self.renders = 0
        self.shade = 1

    async def render(self, context):
        self.renders += 1
        return Image.new("1", (PANEL_WIDTH, PANEL_HEIGHT), self.shade)

    async def stop(self) -> None:
        pass


@pytest.fixture
def client(settings):
    app = create_app(settings)
    app.state.dashboard.renderer = StubRenderer()
    with TestClient(app) as test_client:
        yield test_client


def test_the_image_is_refused_without_a_token(client):
    """Bilden innehåller familjens dag i klartext och står på internet."""
    assert client.get("/dashboard.png").status_code == 401


def test_the_image_is_refused_with_the_wrong_token(client):
    response = client.get("/dashboard.png", headers={"Authorization": "Bearer fel"})
    assert response.status_code == 401


def test_the_image_is_served_with_a_valid_token(client):
    response = client.get("/dashboard.png", headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["ETag"]


def test_an_unchanged_image_answers_304(client):
    first = client.get("/dashboard.png", headers=AUTH)
    again = client.get(
        "/dashboard.png", headers={**AUTH, "If-None-Match": first.headers["ETag"]}
    )
    assert again.status_code == 304
    assert again.content == b""


def test_a_changed_image_gets_a_new_etag(client):
    dashboard = client.app.state.dashboard
    first = client.get("/dashboard.png", headers=AUTH).headers["ETag"]

    dashboard.renderer.shade = 0
    dashboard._frame = None  # tvinga omrendering utan att vänta ut RENDER_TTL

    assert client.get("/dashboard.png", headers=AUTH).headers["ETag"] != first


def test_renders_are_reused_between_requests(client):
    for _ in range(4):
        client.get("/dashboard.png", headers=AUTH)
    assert client.app.state.dashboard.renderer.renders == 1


def test_the_raw_buffer_is_exactly_panel_sized(client):
    response = client.get("/dashboard.bin", headers=AUTH)
    assert response.status_code == 200
    assert len(response.content) == BUFFER_SIZE


def test_health_is_open_but_says_nothing_about_the_family(client):
    client.get("/dashboard.png", headers=AUTH)
    body = client.get("/healthz").json()
    assert body["ok"] is True
    for entry in body["sources"].values():
        assert set(entry) == {"age_seconds", "stale"}


def test_the_server_refuses_to_start_without_a_token(monkeypatch, tmp_path):
    monkeypatch.delenv("DASHBOARD_TOKEN", raising=False)
    with pytest.raises(ConfigError, match="DASHBOARD_TOKEN"):
        load_settings(tmp_path / "saknas.yaml", require_token=True)


def test_a_short_token_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_TOKEN", "hemlis")
    with pytest.raises(ConfigError):
        load_settings(tmp_path / "saknas.yaml", require_token=True)


@pytest.mark.parametrize(
    "header,expected",
    [('"a"', True), ('W/"a"', True), ("*", True), ('"b"', False), (None, False), ('"b", "a"', True)],
)
def test_etag_comparison_handles_the_forms_clients_send(header, expected):
    assert matches(header, '"a"') is expected
