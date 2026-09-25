from fastapi.testclient import TestClient

from app import __version__
from app.config import Settings
from app.factory import create_app


def test_version_matches_package_openapi_and_identity():
    app = create_app(Settings())
    with TestClient(app) as client:
        assert app.version == __version__
        assert client.get("/openapi.json").json()["info"]["version"] == __version__
        assert client.get("/whoami").json()["version"] == __version__
