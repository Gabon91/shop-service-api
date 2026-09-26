from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from dotenv import dotenv_values

from scripts import authorize_gmail


@pytest.fixture
def local_oauth(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "GMAIL_ADDRESS=orders@example.com\n"
        "GOOGLE_CLIENT_ID=test-id\nGOOGLE_CLIENT_SECRET=test-secret\n",
        encoding="utf-8",
    )
    flow = Mock()
    flow.run_local_server.return_value = SimpleNamespace(
        refresh_token="test-refresh-token", token="test-access-token"
    )
    monkeypatch.setattr(
        authorize_gmail.InstalledAppFlow, "from_client_config",
        Mock(return_value=flow),
    )
    return tmp_path, flow


def test_authorization_saves_token_only_after_account_match(
    local_oauth, monkeypatch, capsys
):
    path, flow = local_oauth
    def fake_get(url, **kwargs):
        data = (
            {"scope": "https://www.googleapis.com/auth/gmail.send openid email"}
            if url.endswith("/tokeninfo") else {"email": "orders@example.com"}
        )
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))

    monkeypatch.setattr(authorize_gmail.httpx, "get", fake_get)
    authorize_gmail.main()
    config = dotenv_values(path / ".env")
    assert config["GOOGLE_REFRESH_TOKEN"] == "test-refresh-token"
    scopes = authorize_gmail.InstalledAppFlow.from_client_config.call_args.kwargs["scopes"]
    assert "https://www.googleapis.com/auth/gmail.send" in scopes
    assert "web" in authorize_gmail.InstalledAppFlow.from_client_config.call_args.args[0]
    flow.run_local_server.assert_called_once_with(
        host="127.0.0.1", port=8765, prompt="consent",
        access_type="offline", include_granted_scopes="true",
    )
    assert "test-refresh-token" not in capsys.readouterr().out


def test_authorization_rejects_wrong_account_without_saving_token(
    local_oauth, monkeypatch
):
    path, _ = local_oauth
    def fake_get(url, **kwargs):
        data = (
            {"scope": "https://www.googleapis.com/auth/gmail.send openid email"}
            if url.endswith("/tokeninfo") else {"email": "wrong@example.com"}
        )
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))

    monkeypatch.setattr(authorize_gmail.httpx, "get", fake_get)
    with pytest.raises(SystemExit, match="does not match"):
        authorize_gmail.main()
    assert "GOOGLE_REFRESH_TOKEN" not in dotenv_values(path / ".env")


def test_authorization_rejects_token_without_gmail_send(local_oauth, monkeypatch):
    path, _ = local_oauth
    monkeypatch.setattr(
        authorize_gmail.httpx, "get",
        lambda url, **kwargs: httpx.Response(
            200, json={"scope": "openid email"},
            request=httpx.Request("GET", url),
        ),
    )
    with pytest.raises(SystemExit, match="did not grant gmail.send"):
        authorize_gmail.main()
    assert "GOOGLE_REFRESH_TOKEN" not in dotenv_values(path / ".env")
