from pathlib import Path

import pytest

from spec_council.cli import main
from spec_council.council import Agent, Council, load_council
from spec_council.providers import ProviderError, make_provider

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
SPEC = "# Spec\n\nDo the thing."


def mock_council(rounds=7, stop=True, critics=2):
    p = make_provider("mock", "")
    return Council(
        critics=[Agent(f"Critic {i}", "review", p) for i in range(critics)],
        editor=p,
        rounds=rounds,
        stop_on_consensus=stop,
    )


def test_stops_on_consensus(tmp_path):
    council = mock_council()
    proposed = council.run(SPEC, out_dir=tmp_path, log=lambda *_: None)
    # mock critics ask for changes in rounds 1-2 and approve in round 3
    assert len(council.history) == 3
    assert council.history[-1].consensus
    assert "PROPOSED SPEC: not final" in proposed
    assert "reached consensus" in proposed
    assert (tmp_path / "proposed_spec.md").exists()
    assert (tmp_path / "round_01" / "reviews.md").exists()


def test_round_limit_respected(tmp_path):
    council = mock_council(rounds=2)
    proposed = council.run(SPEC, out_dir=tmp_path, log=lambda *_: None)
    assert len(council.history) == 2
    assert "did not reach consensus" in proposed


def test_editor_revisions_accumulate():
    council = mock_council(rounds=2)
    council.run(SPEC, log=lambda *_: None)
    final = council.history[-1].spec
    assert "round 1" in final and "round 2" in final


def test_load_config():
    council = load_council(EXAMPLES / "agents.mock.toml")
    assert len(council.critics) == 3
    assert council.rounds == 7


def test_unknown_provider():
    with pytest.raises(ProviderError):
        make_provider("nope", "x")


def test_missing_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        make_provider("anthropic", "m").complete("s", "p")


def test_cli_end_to_end(tmp_path):
    code = main([
        "review", str(EXAMPLES / "rate-limiter-spec.md"),
        "--config", str(EXAMPLES / "agents.mock.toml"),
        "--out", str(tmp_path / "run"),
    ])
    assert code == 0
    assert (tmp_path / "run" / "proposed_spec.md").exists()
