import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import fpl_client  # noqa: E402

# Shaped like the real API's payloads, trimmed to the fields we use.
SAMPLE_BOOTSTRAP = {
    "events": [
        {
            "id": 1,
            "name": "Gameweek 1",
            "deadline_time": "2026-08-21T17:30:00Z",
            "deadline_time_epoch": 1786894200,
            "finished": False,
            "is_current": False,
            "is_next": True,
        },
    ],
    "teams": [
        {
            "id": 1,
            "name": "Arsenal",
            "short_name": "ARS",
            "strength": 5,
            "strength_overall_home": 1350,
            "strength_overall_away": 1330,
            "strength_attack_home": 1340,
            "strength_attack_away": 1320,
            "strength_defence_home": 1360,
            "strength_defence_away": 1340,
        },
    ],
    "elements": [
        {
            "id": 1,
            "web_name": "Saka",
            "first_name": "Bukayo",
            "second_name": "Saka",
            "team": 1,
            "element_type": 3,
            "now_cost": 100,
            "form": "6.5",
            "chance_of_playing_next_round": None,
            "minutes": 450,
            "expected_goals": "2.1",
            "expected_assists": "1.8",
            "expected_goal_involvements": "3.9",
            "ict_index": "120.5",
            "status": "a",
        },
    ],
}

SAMPLE_FIXTURES = [
    {
        "id": 1,
        "event": 1,
        "team_h": 1,
        "team_a": 2,
        "team_h_difficulty": 2,
        "team_a_difficulty": 4,
        "kickoff_time": "2026-08-21T19:00:00Z",
        "finished": False,
    },
]


def _mock_response(payload):
    mock = MagicMock()
    mock.json.return_value = payload
    mock.raise_for_status.return_value = None
    return mock


def test_get_players_parses_real_shaped_data(tmp_path, monkeypatch):
    monkeypatch.setattr(fpl_client, "CACHE_DIR", tmp_path)
    with patch("fpl_client.requests.get", return_value=_mock_response(SAMPLE_BOOTSTRAP)):
        players = fpl_client.get_players()

    assert len(players) == 1
    assert players[0].web_name == "Saka"
    assert players[0].price == 10.0  # now_cost 100 -> £10.0m
    assert players[0].expected_goal_involvements == 3.9
    assert players[0].form == 6.5  # coerced from "6.5"


def test_get_teams(tmp_path, monkeypatch):
    monkeypatch.setattr(fpl_client, "CACHE_DIR", tmp_path)
    with patch("fpl_client.requests.get", return_value=_mock_response(SAMPLE_BOOTSTRAP)):
        teams = fpl_client.get_teams()

    assert teams[0].name == "Arsenal"


def test_get_next_gameweek(tmp_path, monkeypatch):
    monkeypatch.setattr(fpl_client, "CACHE_DIR", tmp_path)
    with patch("fpl_client.requests.get", return_value=_mock_response(SAMPLE_BOOTSTRAP)):
        gw = fpl_client.get_next_gameweek()

    assert gw is not None
    assert gw.id == 1
    assert gw.is_next is True


def test_get_all_fixtures(tmp_path, monkeypatch):
    monkeypatch.setattr(fpl_client, "CACHE_DIR", tmp_path)
    with patch("fpl_client.requests.get", return_value=_mock_response(SAMPLE_FIXTURES)):
        fixtures = fpl_client.get_all_fixtures()

    assert len(fixtures) == 1
    assert fixtures[0].team_h_difficulty == 2


def test_falls_back_to_stale_cache_on_network_error(tmp_path, monkeypatch):
    monkeypatch.setattr(fpl_client, "CACHE_DIR", tmp_path)
    tmp_path.mkdir(exist_ok=True)
    cache_file = tmp_path / "bootstrap_static.json"
    cache_file.write_text(json.dumps(SAMPLE_BOOTSTRAP))

    with patch("fpl_client.requests.get", side_effect=fpl_client.requests.RequestException("boom")):
        data = fpl_client.get_bootstrap_static()

    assert data == SAMPLE_BOOTSTRAP


def test_raises_clean_error_with_no_cache_and_network_down(tmp_path, monkeypatch):
    monkeypatch.setattr(fpl_client, "CACHE_DIR", tmp_path)
    with patch("fpl_client.requests.get", side_effect=fpl_client.requests.RequestException("boom")):
        try:
            fpl_client.get_bootstrap_static()
            assert False, "expected FPLClientError"
        except fpl_client.FPLClientError:
            pass
