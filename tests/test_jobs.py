"""Tests for the extension queue.

The queue exists because PRISM blocks IPs that fetch concurrently, and a block
would take the platform's data supply with it. So the properties worth pinning
are not really about jobs: they are that two workers can never fetch at once,
that a visitor cannot start a fetch, and that an unset admin secret fails closed
rather than open.
"""

import pytest

from applebee import api, jobs
from web.app import answer


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    return jobs.JobStore()


def a_weather_job(store, **overrides):
    parameters = {"region": "northeast", "start": "2019-01-01", "end": "2025-12-31"}
    return store.request("weather", requested_by="grower@example.com",
                         **{**parameters, **overrides})


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------


def test_a_request_starts_as_a_request_and_nothing_more(store):
    job = a_weather_job(store)
    assert job.state == jobs.REQUESTED
    assert not job.runnable


def test_a_job_must_name_what_it_needs(store):
    with pytest.raises(ValueError, match="end"):
        store.request("weather", region="northeast", start="2019-01-01")


def test_an_unknown_kind_lists_the_alternatives(store):
    with pytest.raises(ValueError, match="forage"):
        store.request("everything", region="northeast")


def test_a_job_is_planned_before_it_is_approved(store):
    # "About seven hours and 10 GB" is what an administrator needs to know, and
    # answering it must not touch the network.
    plan = store.plan(a_weather_job(store).id)
    assert plan["to_download"] == 5114
    assert plan["approx_hours_at_default_pause"] == pytest.approx(6.4, abs=0.5)


def test_the_command_is_the_script_that_already_does_the_work(store):
    assert jobs.command(a_weather_job(store))[:2] == ["python", "scripts/fetch_prism.py"]


def test_only_an_approved_job_can_be_claimed(store):
    a_weather_job(store)
    assert store.claim() is None            # requested, not approved


def test_the_oldest_approved_job_goes_first(store):
    first, second = a_weather_job(store), a_weather_job(store, end="2020-12-31")
    store.approve(second.id)
    store.approve(first.id)
    assert store.claim().id == first.id     # by request time, not approval time


def test_a_job_records_how_it_got_where_it_is(store):
    job = a_weather_job(store)
    store.approve(job.id, by="edward")
    claimed = store.claim("worker-1")
    store.finish(claimed.id, True, note="5,114 files")
    final = store.get(job.id)
    assert final.state == jobs.DONE and final.note == "5,114 files"
    assert [h["state"] for h in final.history] == ["requested", "approved",
                                                   "running", "done"]


def test_a_state_cannot_be_skipped(store):
    job = a_weather_job(store)
    with pytest.raises(ValueError, match="requested"):
        store.finish(job.id, True)


# ---------------------------------------------------------------------------
# The lock -- the reason any of this exists
# ---------------------------------------------------------------------------


def test_two_workers_cannot_fetch_at_once(store):
    store.approve(a_weather_job(store).id)
    store.approve(a_weather_job(store, end="2020-12-31").id)
    assert store.claim("worker-1") is not None
    with pytest.raises(jobs.Locked):
        store.claim("worker-2")


def test_an_empty_queue_does_not_leave_the_lock_held(store):
    assert store.claim("worker-1") is None
    assert store.claim("worker-2") is None      # would raise Locked if it did


def test_an_abandoned_lock_is_reclaimed(store, monkeypatch):
    store.acquire_lock("worker-that-died")
    monkeypatch.setattr(jobs, "LOCK_STALE_SECONDS", -1)
    store.acquire_lock("worker-2")              # no raise: the old one is stale


def test_a_heartbeat_keeps_a_long_fetch_from_looking_dead(store):
    import json

    store.acquire_lock("worker-1")
    lock = store.root / jobs.LOCK_FILE.name
    lock.write_text(json.dumps({"holder": "worker-1", "at": 0}))
    store.heartbeat()
    assert json.loads(lock.read_text())["at"] > 0


# ---------------------------------------------------------------------------
# Who may do what
# ---------------------------------------------------------------------------


def test_anyone_may_request_but_a_request_runs_nothing(store):
    status, payload = answer("POST", "/api/jobs", {}, {
        "kind": "weather", "requested_by": "grower@example.com",
        "parameters": {"region": "northeast", "start": "2019-01-01",
                       "end": "2025-12-31"}})
    assert status == 200
    assert payload["job"]["state"] == jobs.REQUESTED
    assert payload["plan"]["to_download"] == 5114
    assert "administrator" in payload["note"]


def test_approval_fails_closed_when_no_secret_is_configured(store, monkeypatch):
    monkeypatch.delenv(api.ADMIN_TOKEN_ENV, raising=False)
    job = a_weather_job(store)
    status, payload = answer("POST", f"/api/jobs/{job.id}/approve", {}, {"token": "any"})
    assert status == 403 and "not set" in payload["error"]


def test_a_wrong_token_does_not_approve(store, monkeypatch):
    monkeypatch.setenv(api.ADMIN_TOKEN_ENV, "the-real-one")
    job = a_weather_job(store)
    status, _ = answer("POST", f"/api/jobs/{job.id}/approve", {}, {"token": "guess"})
    assert status == 403
    assert store.get(job.id).state == jobs.REQUESTED


def test_the_right_token_approves_it(store, monkeypatch):
    monkeypatch.setenv(api.ADMIN_TOKEN_ENV, "the-real-one")
    job = a_weather_job(store)
    status, payload = answer("POST", f"/api/jobs/{job.id}/approve", {},
                             {"by": "edward"}, {"X-Admin-Token": "the-real-one"})
    assert status == 200 and payload["job"]["state"] == jobs.APPROVED


def test_the_queue_can_be_read_without_a_token(store):
    a_weather_job(store)
    status, payload = answer("GET", "/api/jobs", {}, None)
    assert status == 200 and len(payload["jobs"]) == 1
