from btb.data import STATIONS, TODAY, TRAINS
from btb.env import Environment, TOOL_SPECS, _ALIAS, tool_specs

D = "2026-10-11"  # "tomorrow" relative to TODAY


def ok(r):  assert r["status"] == "ok", r; return r
def bad(r, code): assert r["status"] == "error" and r["error_code"] == code, r; return r


# ---------- data sanity ----------
def test_aliases_unique_and_complete():
    n_alias = sum(len(set(a + [n])) for n, a in STATIONS.values())
    assert len(_ALIAS) == len({k for k in _ALIAS})
    assert set(_ALIAS.values()) == set(STATIONS)  # every station reachable

def test_train_data_is_consistent():
    nums = [t["number"] for t in TRAINS]
    assert len(nums) == len(set(nums))
    for t in TRAINS:
        kms = [s[3] for s in t["stops"]]
        assert kms == sorted(kms) and kms[0] == 0
        assert t["stops"][0][1] is None and t["stops"][-1][2] is None
        times = []
        for _, arr, dep, _ in t["stops"]:
            times += [x for x in (arr, dep) if x]
        assert times == sorted(times), t["number"]       # time moves forward, same day
        for _, arr, dep, _ in t["stops"]:
            assert all(s[0] in STATIONS for s in t["stops"])

# ---------- determinism / reset ----------
def test_two_envs_give_identical_results():
    a, b = Environment(), Environment()
    q = ("search_trains", dict(origin="MMCT", destination="ADI", date=D))
    assert a.call(*q) == b.call(*q)

def test_reset_restores_baseline():
    env = Environment(); base = env.snapshot()
    ok(env.call("book_ticket", dict(train_number="90108", date=D, origin="MMCT",
        destination="ADI", travel_class="3A", passenger_name="Asha Rao")))
    assert env.snapshot() != base
    env.reset()
    assert env.snapshot() == base

# ---------- resolve_station ----------
def test_resolve_station_aliases():
    env = Environment()
    for q, code in [("Bombay", "MMCT"), ("  AHMEDABAD ", "ADI"), ("amdavad", "ADI"),
                    ("Dilli", "NDLS"), ("bangalore", "SBC"), ("Mumbai Central", "MMCT")]:
        assert ok(env.call("resolve_station", {"query": q}))["station_code"] == code
    bad(env.call("resolve_station", {"query": "Atlantis"}), "STATION_NOT_FOUND")

# ---------- search_trains ----------
def test_search_with_time_window_is_sorted_and_correct():
    env = Environment()
    r = ok(env.call("search_trains", dict(origin="MMCT", destination="ADI", date=D, depart_after="18:00")))
    assert [t["train_number"] for t in r["trains"]] == ["90103", "90108"]
    assert r["trains"][0]["departure"] == "18:20" and r["trains"][0]["arrival"] == "23:55"

def test_search_respects_direction():
    env = Environment()
    r = ok(env.call("search_trains", dict(origin="ADI", destination="MMCT", date=D)))
    assert [t["train_number"] for t in r["trains"]] == ["90104", "90105"]

def test_search_no_route_is_empty_not_error():
    env = Environment()
    r = ok(env.call("search_trains", dict(origin="PUNE", destination="JP", date=D)))
    assert r["count"] == 0 and r["trains"] == []

def test_search_requires_codes_not_names():
    env = Environment()
    bad(env.call("search_trains", dict(origin="Mumbai", destination="ADI", date=D)), "STATION_NOT_FOUND")

def test_search_intermediate_stops():
    env = Environment()
    r = ok(env.call("search_trains", dict(origin="ST", destination="ADI", date=D)))
    assert {t["train_number"] for t in r["trains"]} == {"90101", "90102", "90103"}

# ---------- dates / formats ----------
def test_date_validation():
    env = Environment()
    for d, code in [("11-10-2026", "INVALID_DATE"), ("2026-02-30", "INVALID_DATE"),
                    ("2026-10-09", "INVALID_DATE"), ("2026-12-25", "INVALID_DATE")]:
        bad(env.call("search_trains", dict(origin="MMCT", destination="ADI", date=d)), code)
    bad(env.call("search_trains", dict(origin="MMCT", destination="ADI", date=D, depart_after="6pm")), "INVALID_TIME")

# ---------- details / availability / fare ----------
def test_train_details():
    r = ok(Environment().call("get_train_details", {"train_number": "90101"}))
    assert [s["station"] for s in r["stops"]] == ["MMCT", "ST", "BRC", "ADI"]
    bad(Environment().call("get_train_details", {"train_number": "12345"}), "TRAIN_NOT_FOUND")

def test_availability_and_class_validation():
    env = Environment()
    assert ok(env.call("check_availability", dict(train_number="90103", date=D, travel_class="3A")))["seats_available"] == 0
    assert ok(env.call("check_availability", dict(train_number="90108", date=D, travel_class="3a")))["seats_available"] == 18
    bad(env.call("check_availability", dict(train_number="90106", date=D, travel_class="2A")), "INVALID_CLASS")
    bad(env.call("check_availability", dict(train_number="90106", date=D, travel_class="XX")), "INVALID_CLASS")

def test_fare():
    env = Environment()
    assert ok(env.call("get_fare", dict(train_number="90108", origin="MMCT", destination="ADI", travel_class="3A")))["fare_per_passenger"] == 589
    # partial segment: Surat -> Ahmedabad on 90101 SL = 0.5 * (491-263)
    assert ok(env.call("get_fare", dict(train_number="90101", origin="ST", destination="ADI", travel_class="SL")))["fare_per_passenger"] == 114
    # half-rupee case rounds UP: SL MMCT->ADI = 245.5 -> 246 ; ST->BRC = 64.5 -> 65
    assert ok(env.call("get_fare", dict(train_number="90108", origin="MMCT", destination="ADI", travel_class="SL")))["fare_per_passenger"] == 246
    assert ok(env.call("get_fare", dict(train_number="90101", origin="ST", destination="BRC", travel_class="SL")))["fare_per_passenger"] == 65
    bad(env.call("get_fare", dict(train_number="90108", origin="ADI", destination="MMCT", travel_class="3A")), "INVALID_ROUTE")

# ---------- book_ticket (state-changing) ----------
BOOK = dict(train_number="90108", date=D, origin="MMCT", destination="ADI",
            travel_class="3A", passenger_name="Asha Rao")

def test_booking_changes_state():
    env = Environment()
    r = ok(env.call("book_ticket", {**BOOK, "num_passengers": 2}))
    assert r["booking_id"] == "PNR0001" and r["total_fare"] == 589 * 2
    assert env.seats[("90108", "3A")] == 16
    assert ok(env.call("book_ticket", BOOK))["booking_id"] == "PNR0002"
    assert len(env.snapshot()["bookings"]) == 2

def test_sold_out_booking_fails_and_changes_nothing():
    env = Environment(); before = env.snapshot()
    bad(env.call("book_ticket", {**BOOK, "train_number": "90103"}), "SOLD_OUT")
    assert env.snapshot() == before

def test_failed_booking_never_changes_state():
    env = Environment(); before = env.snapshot()
    bad(env.call("book_ticket", {**BOOK, "origin": "ADI", "destination": "MMCT"}), "INVALID_ROUTE")
    bad(env.call("book_ticket", {**BOOK, "passenger_name": "  "}), "INVALID_PASSENGER")
    bad(env.call("book_ticket", {**BOOK, "num_passengers": 9}), "INVALID_PASSENGERS")
    bad(env.call("book_ticket", {**BOOK, "date": "2026-10-01"}), "INVALID_DATE")
    assert env.snapshot() == before

# ---------- argument validation / specs ----------
def test_bad_calls_become_error_observations_not_exceptions():
    env = Environment()
    bad(env.call("fly_plane", {}), "UNKNOWN_TOOL")
    bad(env.call("resolve_station", {}), "INVALID_ARGUMENTS")
    bad(env.call("resolve_station", {"query": "x", "foo": 1}), "INVALID_ARGUMENTS")
    bad(env.call("resolve_station", {"query": 5}), "INVALID_ARGUMENTS")
    bad(env.call("book_ticket", {**BOOK, "num_passengers": "2"}), "INVALID_ARGUMENTS")
    bad(env.call("resolve_station", "Mumbai"), "INVALID_ARGUMENTS")

def test_six_tools_with_specs():
    assert set(TOOL_SPECS) == {"resolve_station", "search_trains", "get_train_details",
                               "check_availability", "get_fare", "book_ticket"}
    assert len(tool_specs()) == 6
