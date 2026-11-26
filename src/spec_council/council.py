"""The review loop: critics review the spec, an editor revises it, repeat."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .providers import Provider, make_provider

CRITIC_SYSTEM = """You are {name}, a reviewer on a spec review council.
Your role: {role}

Review the specification you are given from your role's point of view.
Start your answer with exactly one line: "VERDICT: APPROVE" or "VERDICT: REVISE".
Then list concrete issues as bullets. Quote the part of the spec each issue is about.
Only raise issues that matter. Approve when nothing blocking is left."""

EDITOR_SYSTEM = """You are the editor of a technical specification.
You receive the current spec and reviews from several reviewers.
Produce a revised spec that addresses the valid issues. Keep the original structure,
intent and wording where nothing needs to change. Do not invent requirements
nobody asked for. Return only the full revised spec in Markdown, nothing else."""

VERDICT_RE = re.compile(r"VERDICT:\s*(APPROVE|REVISE)", re.IGNORECASE)


@dataclass
class Agent:
    name: str
    role: str
    provider: Provider

    def review(self, spec: str, round_no: int, rounds: int) -> "Review":
        prompt = (
            f"Review round {round_no} of {rounds}.\n\n<spec>\n{spec}\n</spec>"
        )
        text = self.provider.complete(CRITIC_SYSTEM.format(name=self.name, role=self.role), prompt)
        match = VERDICT_RE.search(text)
        approved = bool(match and match.group(1).upper() == "APPROVE")
        return Review(agent=self.name, approved=approved, text=text.strip())


@dataclass
class Review:
    agent: str
    approved: bool
    text: str


@dataclass
class RoundResult:
    number: int
    reviews: list[Review]
    spec: str

    @property
    def consensus(self) -> bool:
        return all(r.approved for r in self.reviews)


@dataclass
class Council:
    critics: list[Agent]
    editor: Provider
    rounds: int = 7
    stop_on_consensus: bool = True
    history: list[RoundResult] = field(default_factory=list)

    def run(self, spec: str, out_dir: Path | None = None, log=print) -> str:
        current = spec
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "00_input_spec.md").write_text(spec, encoding="utf-8")

        for n in range(1, self.rounds + 1):
            log(f"Round {n}/{self.rounds}: {len(self.critics)} reviewers")
            reviews = [c.review(current, n, self.rounds) for c in self.critics]
            for r in reviews:
                log(f"  {r.agent}: {'APPROVE' if r.approved else 'REVISE'}")

            if all(r.approved for r in reviews):
                result = RoundResult(n, reviews, current)
                self.history.append(result)
                self._write_round(out_dir, result)
                if self.stop_on_consensus:
                    log(f"Consensus reached in round {n}.")
                    break
                continue

            current = self._revise(current, reviews, n).strip()
            result = RoundResult(n, reviews, current)
            self.history.append(result)
            self._write_round(out_dir, result)

        proposed = proposal_header(self.history) + current
        if out_dir:
            (out_dir / "proposed_spec.md").write_text(proposed, encoding="utf-8")
        return proposed

    def _revise(self, spec: str, reviews: list[Review], n: int) -> str:
        feedback = "\n\n".join(f"### {r.agent}\n{r.text}" for r in reviews)
        prompt = (
            f"Review round {n} of {self.rounds}.\n\n<spec>\n{spec}\n</spec>\n\n"
            f"<reviews>\n{feedback}\n</reviews>"
        )
        return self.editor.complete(EDITOR_SYSTEM, prompt)

    @staticmethod
    def _write_round(out_dir: Path | None, result: RoundResult) -> None:
        if not out_dir:
            return
        d = out_dir / f"round_{result.number:02d}"
        d.mkdir(exist_ok=True)
        reviews = "\n\n".join(
            f"## {r.agent} ({'APPROVE' if r.approved else 'REVISE'})\n\n{r.text}"
            for r in result.reviews
        )
        (d / "reviews.md").write_text(f"# Round {result.number} reviews\n\n{reviews}\n", encoding="utf-8")
        (d / "spec.md").write_text(result.spec, encoding="utf-8")


def proposal_header(history: list[RoundResult]) -> str:
    n = len(history)
    status = "reached consensus" if history and history[-1].consensus else "did not reach consensus"
    return (
        "<!--\n"
        "PROPOSED SPEC: not final.\n"
        f"Produced by spec-council after {n} round(s); the reviewers {status}.\n"
        "A person must review and accept this before it becomes the spec.\n"
        "-->\n\n"
    )


def load_council(config_path: Path, rounds: int | None = None) -> Council:
    cfg = tomllib.loads(config_path.read_text(encoding="utf-8"))
    critics = [
        Agent(
            name=a["name"],
            role=a["role"],
            provider=make_provider(a["provider"], a.get("model", "")),
        )
        for a in cfg.get("agents", [])
    ]
    if not critics:
        raise ValueError("Config needs at least one [[agents]] entry.")
    ed = cfg.get("editor", {})
    editor = make_provider(ed.get("provider", critics[0].provider.name), ed.get("model", critics[0].provider.model))
    run = cfg.get("run", {})
    return Council(
        critics=critics,
        editor=editor,
        rounds=rounds or run.get("rounds", 7),
        stop_on_consensus=run.get("stop_on_consensus", True),
    )
