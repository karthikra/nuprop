"""Tracks the known structural 'proposal field persistence' bug.

This is the larger issue behind the milestone note "some fields don't persist
due to session commit ordering". It is NOT a logic error in a single function —
it is structural:

  * ``get_db()`` opens one ``AsyncSession`` per HTTP request and commits exactly
    once, after the route handler returns.
  * ``approve_gate()`` runs the entire downstream pipeline (research ->
    benchmarks -> cost model -> narrative) inside that single request, each step
    calling Claude and emitting mid-pipeline WebSocket broadcasts.
  * None of the ``proposal_repo.update(...)`` writes are committed yet, so a
    client that reacts to a "phase done" WS event by issuing a fresh REST
    request reads the pre-pipeline row — a read-your-writes violation across
    sessions (on SQLite a second connection cannot see another connection's
    uncommitted writes at all).

The fix is to run each pipeline phase as its own background job with its own
session that commits when the phase finishes — a structural change (building out
the currently-empty ``app/workers/`` package) that is intentionally out of scope
for the test-suite work. This test is kept skipped so the issue stays tracked.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(
    reason="Known structural bug — needs the background-worker pipeline refactor; "
    "see this module's docstring"
)
async def test_pipeline_phases_commit_before_broadcasting_phase_done():
    """When implemented: each pipeline phase must commit its proposal-field
    writes *before* the corresponding 'phase done' WebSocket broadcast fires, so
    a concurrent REST read observes the freshly written research / benchmarks /
    cost_model / narrative fields instead of stale pre-pipeline values."""
    raise AssertionError("not implemented — background-worker pipeline does not exist yet")
