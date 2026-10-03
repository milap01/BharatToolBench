import json
from collections import Counter

from btb.data import STATIONS
from btb.env import Environment
from btb.generate import build_all
from btb.schema import read_jsonl, validate_task, write_jsonl

TASKS = build_all()
EXPECTED_COUNTS = {"L1": 8, "L2": 8, "L3": 10, "ERR": 8, "UND": 6}


def test_counts_and_unique_ids():
    assert dict(Counter(t.category for t in TASKS)) == EXPECTED_COUNTS
    ids = [t.semantic_id for t in TASKS]
    assert len(ids) == len(set(ids)) == 40

def test_every_task_valid():
    for t in TASKS:
        assert validate_task(t) == [], t.semantic_id

def test_generation_is_deterministic(tmp_path=None):
    import tempfile, os
    d = tempfile.mkdtemp()
    write_jsonl(build_all(), os.path.join(d, "a.jsonl")); write_jsonl(build_all(), os.path.join(d, "b.jsonl"))
    assert open(os.path.join(d, "a.jsonl")).read() == open(os.path.join(d, "b.jsonl")).read()

def test_jsonl_roundtrip():
    import tempfile, os
    p = os.path.join(tempfile.mkdtemp(), "t.jsonl"); write_jsonl(TASKS, p)
    assert [t.to_dict() for t in read_jsonl(p)] == [t.to_dict() for t in TASKS]

def test_committed_file_matches_generator():
    assert [t.to_dict() for t in read_jsonl("data/semantic_tasks.jsonl")] == [t.to_dict() for t in TASKS]

def test_no_half_rupee_ambiguity_anywhere():
    # fares use exact integer arithmetic; sanity-check that rule against the env
    from btb.data import RATE_X10
    env = Environment()
    r = env.call("get_fare", dict(train_number="90101", origin="ST", destination="BRC", travel_class="SL"))
    assert r["fare_per_passenger"] == (RATE_X10["SL"] * (392 - 263) + 5) // 10 == 65


# ---------- oracle replay: gold steps, executed for real, must reproduce the gold ----------
def _values(o):
    if isinstance(o, dict):
        for v in o.values(): yield from _values(v)
    elif isinstance(o, list):
        for v in o: yield from _values(v)
    else:
        yield o

def _replay(t):
    env = Environment(); obs = []
    for s in t.gold.core_steps:
        alt = s["any_of"][0]
        if alt["tool"] == "resolve_station":
            args = {"query": STATIONS[alt["args"]["resolves_to"]][0]}
        else:
            args = alt["args"]
        r = env.call(alt["tool"], args)
        obs.append(r)
    return env, obs

def test_oracle_replay_reproduces_gold_state_and_answer_values():
    for t in TASKS:
        env, obs = _replay(t)
        state = [{k: v for k, v in b.items() if k != "booking_id"} for b in env.snapshot()["bookings"]]
        assert state == t.gold.expected_bookings, t.semantic_id
        seen = set(map(str, _values(obs)))
        for k in ("train_number", "travel_class", "fare", "seats_available", "station_code",
                  "departure_time", "arrival_time"):
            if k in t.gold.expected_answer:
                assert str(t.gold.expected_answer[k]) in seen, (t.semantic_id, k)
        # no gold step may itself produce an error, except deliberate failing attempts in ERR tasks
        if t.category != "ERR":
            assert all(o["status"] == "ok" for o in obs), t.semantic_id

def test_state_changing_tasks_are_exactly_the_booked_ones():
    for t in TASKS:
        assert (t.gold.expected_answer["status"] == "booked") == bool(t.gold.expected_bookings)
    assert sum(bool(t.gold.expected_bookings) for t in TASKS) == 7   # L2-06,07,08 L3-04,06,09 ERR-03

def test_dependencies_exist_in_multistep_tasks():
    n_dep = sum(any(s["depends_on"] for s in t.gold.core_steps) for t in TASKS)
    assert n_dep >= 20

def test_L3_constraints_are_machine_checkable_and_satisfied_by_gold():
    env = Environment()
    for t in TASKS:
        if t.category != "L3": continue
        c, a = t.constraints, t.gold.expected_answer
        r = env.call("search_trains", dict(origin=c["origin"], destination=c["destination"], date=c["date"]))
        row = next(x for x in r["trains"] if x["train_number"] == a["train_number"])
        if "depart_after" in c:   assert row["departure"] > c["depart_after"]
        if "depart_before" in c:  assert row["departure"] < c["depart_before"]
        if "arrive_before" in c:  assert row["arrival"] < c["arrive_before"]
        assert a["travel_class"] in c["classes"]
