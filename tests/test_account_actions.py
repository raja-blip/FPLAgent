import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import fpl_actions  # noqa: E402
import fpl_auth  # noqa: E402
import telegram_notifier  # noqa: E402


# ---- fpl_auth ----

def test_login_raises_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("FPL_EMAIL", raising=False)
    monkeypatch.delenv("FPL_PASSWORD", raising=False)
    with pytest.raises(fpl_auth.FPLAuthError):
        fpl_auth.login()


def test_login_raises_when_no_session_cookie_returned(monkeypatch):
    monkeypatch.setenv("FPL_EMAIL", "test@example.com")
    monkeypatch.setenv("FPL_PASSWORD", "hunter2")

    mock_session = MagicMock()
    mock_session.cookies.get_dict.return_value = {}  # no pl_profile
    with patch("fpl_auth.requests.Session", return_value=mock_session):
        with pytest.raises(fpl_auth.FPLAuthError):
            fpl_auth.login()


def test_login_succeeds_with_session_cookie(monkeypatch):
    monkeypatch.setenv("FPL_EMAIL", "test@example.com")
    monkeypatch.setenv("FPL_PASSWORD", "hunter2")

    mock_session = MagicMock()
    mock_session.cookies.get_dict.return_value = {"pl_profile": "abc123"}
    with patch("fpl_auth.requests.Session", return_value=mock_session):
        session = fpl_auth.login()

    assert session is mock_session


def test_get_team_id_reads_env(monkeypatch):
    monkeypatch.setenv("FPL_TEAM_ID", "3670200")
    assert fpl_auth.get_team_id() == "3670200"


# ---- fpl_actions ----

def test_get_current_squad_calls_correct_url():
    mock_session = MagicMock()
    mock_session.get.return_value.json.return_value = {"picks": []}

    fpl_actions.get_current_squad(mock_session, "3670200")

    called_url = mock_session.get.call_args[0][0]
    assert "3670200" in called_url
    assert "my-team" in called_url


def test_submit_transfers_builds_correct_payload():
    mock_session = MagicMock()
    mock_session.post.return_value.json.return_value = {}

    fpl_actions.submit_transfers(
        mock_session, "3670200",
        transfers_out=[10, 20], transfers_in=[30, 40],
        current_gameweek=1,
    )

    payload = mock_session.post.call_args.kwargs["json"]
    assert payload["confirmed"] is True
    assert payload["entry"] == 3670200
    assert payload["event"] == 1
    assert payload["transfers"] == [
        {"element_in": 30, "element_out": 10, "purchase_price": None, "selling_price": None},
        {"element_in": 40, "element_out": 20, "purchase_price": None, "selling_price": None},
    ]


def test_submit_transfers_rejects_mismatched_lengths():
    mock_session = MagicMock()
    with pytest.raises(ValueError):
        fpl_actions.submit_transfers(
            mock_session, "3670200",
            transfers_out=[10, 20], transfers_in=[30],
            current_gameweek=1,
        )


def test_submit_lineup_marks_captain_and_vice_correctly():
    mock_session = MagicMock()
    mock_session.post.return_value.json.return_value = {}

    fpl_actions.submit_lineup(
        mock_session, "3670200",
        starting_ids=[1, 2, 3], bench_ids=[4],
        captain_id=2, vice_captain_id=1,
    )

    payload = mock_session.post.call_args.kwargs["json"]
    picks = {p["element"]: p for p in payload["picks"]}

    assert picks[2]["is_captain"] is True
    assert picks[1]["is_vice_captain"] is True
    assert picks[3]["is_captain"] is False
    assert picks[4]["position"] == 4  # bench player gets the last position slot


# ---- telegram_notifier ----

def test_send_message_uses_correct_token_and_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999888777")

    with patch("telegram_notifier.requests.post") as mock_post:
        mock_post.return_value.raise_for_status.return_value = None
        telegram_notifier.send_message("hello")

    called_url = mock_post.call_args[0][0]
    called_json = mock_post.call_args.kwargs["json"]
    assert "test-token" in called_url
    assert called_json["chat_id"] == "999888777"
    assert called_json["text"] == "hello"
