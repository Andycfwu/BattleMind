import asyncio
import json

from poke_env import AccountConfiguration

from battlemind.reporting import JsonlWriter
from battlemind.runner import LocalPlayer, MatchState


def test_batched_future_message_is_not_in_predecision_snapshot(tmp_path, turn_request, battle, tracker):
    async def exercise():
        decisions = JsonlWriter(tmp_path / "decisions.jsonl")
        events = JsonlWriter(tmp_path / "events.jsonl")
        state = MatchState(0, 30, decisions, events)
        player = LocalPlayer(policy_name="random", seed=42, side="a", state=state,
                             account_configuration=AccountConfiguration("offline", None),
                             start_listening=False, loop=asyncio.get_running_loop())
        player._battles[battle.battle_tag] = battle
        player.trackers[battle.battle_tag] = tracker
        sent = []

        async def capture(message, room=None):
            sent.append(message)

        player.ps_client.send_message = capture
        await player._handle_battle_message([
            [">" + battle.battle_tag], ["", "request", json.dumps(turn_request)],
            ["", "move", "p2a: secret-nickname", "Surf", "p1a: AliasA"],
        ])
        decisions.close()
        events.close()
        row = json.loads((tmp_path / "decisions.jsonl").read_text())
        assert row["observation"]["opponent_revealed"][0]["moves"] == []
        assert tracker.opponents()[0].moves == ("surf",)
        assert sent == [row["command"]]
        assert state.reason is None

    asyncio.run(exercise())


def test_invalid_server_choice_is_visible_and_never_silently_retried(tmp_path, battle):
    async def exercise():
        decisions = JsonlWriter(tmp_path / "decisions.jsonl")
        events = JsonlWriter(tmp_path / "events.jsonl")
        state = MatchState(0, 30, decisions, events)
        player = LocalPlayer(policy_name="random", seed=42, side="a", state=state,
                             account_configuration=AccountConfiguration("offline-error", None),
                             start_listening=False, loop=asyncio.get_running_loop())
        await player._handle_battle_message([[">" + battle.battle_tag],
            ["", "error", "[Invalid choice] move is disabled"]])
        assert state.reason == "crash" and state.invalid_actions == 1
        assert state.decisions == 0
        decisions.close()
        events.close()
        assert json.loads((tmp_path / "events.jsonl").read_text())["kind"] == "server_error"

    asyncio.run(exercise())
