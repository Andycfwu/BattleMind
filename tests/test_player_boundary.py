import asyncio
import json
import pytest

from poke_env import AccountConfiguration

from battlemind.reporting import JsonlWriter
from battlemind.runner import LocalPlayer, MatchState


@pytest.mark.parametrize("policy_name", ["random", "switch-context", "switch-logistic"])
def test_batched_future_message_is_not_in_predecision_snapshot(tmp_path, turn_request, battle, tracker, policy_name):
    async def exercise():
        decisions = JsonlWriter(tmp_path / "decisions.jsonl")
        events = JsonlWriter(tmp_path / "events.jsonl")
        state = MatchState(0, 30, decisions, events)
        from battlemind.prediction import Context, estimate_counts
        counts = estimate_counts([(Context("other", "healthy", "resisted"), 1)] * 10)
        if policy_name == "switch-logistic":
            from battlemind.adapter import snapshot_request
            from battlemind.supervised import LogisticModel, PredictorBundle, features_from_snapshot
            from battlemind.supervised_training import fit_preprocessor
            prep = fit_preprocessor([features_from_snapshot(snapshot_request(turn_request, 1, tracker)[0])])
            counts = PredictorBundle(counts, LogisticModel(prep, (0.0,) * len(prep.columns), 0.0, 0.1), "a" * 64)
        player = LocalPlayer(policy_name=policy_name, counts=counts, seed=42, side="a", state=state,
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
