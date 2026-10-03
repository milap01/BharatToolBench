"""Build the 40 semantic tasks. Gold = computed by running the fixed Environment.
Run:  python -m btb.generate      ->  data/semantic_tasks.jsonl
"""
import os

from .env import Environment
from .schema import Gold, SemanticTask, validate_task, write_jsonl

DATES = {"tomorrow": "2026-10-11",
         "the day after tomorrow": "2026-10-12",
         "on 15 October": "2026-10-15"}
CLS = {"SL": "sleeper", "CC": "chair car", "3A": "3AC", "2A": "2AC", "1A": "first AC"}


# ---------------------------------------------------------------- oracle helpers
def run(tool, **args):
    """Ask the FRESH baseline environment. This is the source of every gold value."""
    r = Environment().call(tool, args)
    assert r["status"] == "ok", (tool, args, r)
    return r

def code(place):
    return run("resolve_station", query=place)["station_code"]

def tm(hhmm):
    h = int(hhmm[:2]); assert hhmm[3:] == "00"
    return "noon" if h == 12 else f"{h} AM" if h < 12 else f"{h - 12} PM"

def step(sid, tool, args, deps=()):
    return {"id": sid, "any_of": [{"tool": tool, "args": args}], "depends_on": list(deps)}

def any_step(sid, alts, deps=()):
    return {"id": sid, "any_of": [{"tool": t, "args": a} for t, a in alts], "depends_on": list(deps)}

def resolves(o, d):
    return [step("r1", "resolve_station", {"resolves_to": o}),
            step("r2", "resolve_station", {"resolves_to": d})]

def book_args(train, date, o, d, cls, name, n):
    return dict(train_number=train, date=date, origin=o, destination=d,
                travel_class=cls, passenger_name=name, num_passengers=n)

def booking_state(args):
    r = run("book_ticket", **args)
    return {k: v for k, v in r.items() if k not in ("status", "booking_id")}

def mk(sid, cat, family, english, slots, answer, steps, bookings=(), constraints=None):
    return SemanticTask(sid, cat, family, english, slots, constraints or {},
                        Gold(answer, list(bookings), steps))

def tickets(n):  # "1 ticket" / "2 tickets"
    return f"{n} ticket" + ("s" if n != 1 else "")


# ---------------------------------------------------------------- L1: single tool
def l1_resolve(sid, place, text):
    c = code(place)
    return mk(sid, "L1", "resolve", text.format(place=place), dict(place=place),
              {"status": "answered", "station_code": c},
              [step("s1", "resolve_station", {"resolves_to": c})])

def l1_avail(sid, train, cls, date_text, text):
    date = DATES[date_text]; seats = run("check_availability", train_number=train, date=date, travel_class=cls)["seats_available"]
    return mk(sid, "L1", "availability", text.format(cls=CLS[cls], train=train, date=date_text),
              dict(train=train, cls=cls, date_text=date_text, date=date),
              {"status": "answered", "seats_available": seats},
              [step("s1", "check_availability", dict(train_number=train, date=date, travel_class=cls))])

def l1_fare(sid, train, o, d, cls, text):
    fare = run("get_fare", train_number=train, origin=o, destination=d, travel_class=cls)["fare_per_passenger"]
    return mk(sid, "L1", "fare", text.format(cls=CLS[cls], train=train, o=o, d=d),
              dict(train=train, origin=o, destination=d, cls=cls),
              {"status": "answered", "fare": fare},
              [step("s1", "get_fare", dict(train_number=train, origin=o, destination=d, travel_class=cls))])

def l1_details(sid, train, which, text):
    stops = run("get_train_details", train_number=train)["stops"]
    ans = {"status": "answered", ("arrival_time" if which == "arr" else "departure_time"):
           stops[-1]["arrival"] if which == "arr" else stops[0]["departure"]}
    return mk(sid, "L1", "details", text.format(train=train), dict(train=train), ans,
              [step("s1", "get_train_details", dict(train_number=train))])


# ---------------------------------------------------------------- L2: sequential
def l2_pick(sid, o_text, d_text, date_text, latest, text):
    o, d, date = code(o_text), code(d_text), DATES[date_text]
    ts = run("search_trains", origin=o, destination=d, date=date)["trains"]
    deps = sorted(t["departure"] for t in ts); assert len(set(deps)) == len(deps)
    pick = ts[-1] if latest else ts[0]
    return mk(sid, "L2", "pick_by_time", text.format(o=o_text, d=d_text, date=date_text),
              dict(origin_text=o_text, dest_text=d_text, date_text=date_text, date=date),
              {"status": "answered", "train_number": pick["train_number"]},
              resolves(o, d) + [step("s1", "search_trains", dict(origin=o, destination=d, date=date), ["r1", "r2"])])

def l2_seats(sid, o_text, d_text, cls, date_text, text):
    o, d, date = code(o_text), code(d_text), DATES[date_text]
    ts = run("search_trains", origin=o, destination=d, date=date)["trains"]; assert len(ts) == 1
    tr = ts[0]["train_number"]
    seats = run("check_availability", train_number=tr, date=date, travel_class=cls)["seats_available"]
    return mk(sid, "L2", "seats_via_search", text.format(cls=CLS[cls], o=o_text, d=d_text, date=date_text),
              dict(origin_text=o_text, dest_text=d_text, cls=cls, date_text=date_text, date=date),
              {"status": "answered", "train_number": tr, "seats_available": seats},
              resolves(o, d) + [step("s1", "search_trains", dict(origin=o, destination=d, date=date), ["r1", "r2"]),
                                step("s2", "check_availability", dict(train_number=tr, date=date, travel_class=cls), ["s1"])])

def l2_fare(sid, o_text, d_text, train, cls, text):
    o, d = code(o_text), code(d_text)
    fare = run("get_fare", train_number=train, origin=o, destination=d, travel_class=cls)["fare_per_passenger"]
    return mk(sid, "L2", "fare_via_resolve", text.format(cls=CLS[cls], o=o_text, d=d_text, train=train),
              dict(origin_text=o_text, dest_text=d_text, train=train, cls=cls),
              {"status": "answered", "fare": fare},
              resolves(o, d) + [step("s1", "get_fare", dict(train_number=train, origin=o, destination=d, travel_class=cls), ["r1", "r2"])])

def l2_book(sid, o_text, d_text, train, cls, date_text, name, n, text):
    o, d, date = code(o_text), code(d_text), DATES[date_text]
    ba = book_args(train, date, o, d, cls, name, n)
    return mk(sid, "L2", "book_via_resolve",
              text.format(t=tickets(n), cls=CLS[cls], train=train, o=o_text, d=d_text, date=date_text, name=name),
              dict(origin_text=o_text, dest_text=d_text, train=train, cls=cls, date_text=date_text, date=date, name=name, n=n),
              {"status": "booked", "train_number": train, "travel_class": cls},
              resolves(o, d) + [step("b1", "book_ticket", ba, ["r1", "r2"])], [booking_state(ba)])


# ---------------------------------------------------------------- L3: constraint reasoning
def l3(sid, o_text, d_text, date_text, classes, text, after=None, before=None, arrive_before=None,
       max_fare=None, check_seats=False, check_fare=False, book=None):
    """Solver enumerates (train, class) pairs; the constraint set must leave EXACTLY ONE."""
    o, d, date = code(o_text), code(d_text), DATES[date_text]
    n = book["n"] if book else 1
    cands = []
    for t in run("search_trains", origin=o, destination=d, date=date)["trains"]:
        dep, arr = t["departure"], t["arrival"]
        assert dep not in (after, before) and arr != arrive_before      # no boundary ties
        if (after and dep < after) or (before and dep > before) or (arrive_before and arr > arrive_before):
            continue
        for c in t["classes"]:
            if c not in classes: continue
            seats = run("check_availability", train_number=t["train_number"], date=date, travel_class=c)["seats_available"]
            fare = run("get_fare", train_number=t["train_number"], origin=o, destination=d, travel_class=c)["fare_per_passenger"]
            assert fare != max_fare
            if seats < n or (max_fare is not None and fare > max_fare): continue
            cands.append((t["train_number"], c, fare))
    assert len(cands) == 1, (sid, cands)
    tr, c, fare = cands[0]
    steps = resolves(o, d) + [step("s1", "search_trains", dict(origin=o, destination=d, date=date), ["r1", "r2"])]
    if check_seats:
        steps.append(step("c1", "check_availability", dict(train_number=tr, date=date, travel_class=c), ["s1"]))
    if check_fare:
        steps.append(step("f1", "get_fare", dict(train_number=tr, origin=o, destination=d, travel_class=c), ["s1"]))
    bookings = []
    if book:
        ba = book_args(tr, date, o, d, c, book["name"], n)
        steps.append(step("b1", "book_ticket", ba, ["r1", "r2", "s1"])); bookings = [booking_state(ba)]
        ans = {"status": "booked", "train_number": tr, "travel_class": c}
    else:
        ans = {"status": "answered", "train_number": tr, "travel_class": c}
        if check_fare: ans["fare"] = fare
    cons = {k: v for k, v in dict(origin=o, destination=d, date=date, depart_after=after, depart_before=before,
            arrive_before=arrive_before, classes=sorted(classes), min_seats=n, max_fare=max_fare).items() if v is not None}
    slots = dict(origin_text=o_text, dest_text=d_text, date_text=date_text, date=date)
    if book: slots.update(name=book["name"], n=n)
    return mk(sid, "L3", "constraints_book" if book else "constraints_find", text, slots, ans, steps, bookings, cons)


# ---------------------------------------------------------------- ERR: error recovery
def err_attempt(sid, train, cls, o_text, d_text, date_text, name, text, family):
    """Booking that cannot succeed (sold out / class not offered): correct = no booking, report honestly."""
    o, d, date = code(o_text), code(d_text), DATES[date_text]
    ba = book_args(train, date, o, d, cls, name, 1)
    r = Environment().call("book_ticket", ba); assert r["status"] == "error", r      # gold: it really fails
    alts = [("check_availability", dict(train_number=train, date=date, travel_class=cls)),
            ("get_train_details", dict(train_number=train)), ("book_ticket", ba)]
    if family == "sold_out": alts = [alts[0], alts[2]]
    return mk(sid, "ERR", family, text, dict(origin_text=o_text, dest_text=d_text, train=train, cls=cls,
              date_text=date_text, date=date, name=name, failure=r["error_code"]),
              {"status": "no_option"}, [any_step("s1", alts)])

def err_fallback(sid, train, first, second, o_text, d_text, date_text, name, text):
    o, d, date = code(o_text), code(d_text), DATES[date_text]
    first_args = book_args(train, date, o, d, first, name, 1)
    assert Environment().call("book_ticket", first_args)["status"] == "error"
    ba = book_args(train, date, o, d, second, name, 1)
    return mk(sid, "ERR", "fallback_class", text,
              dict(origin_text=o_text, dest_text=d_text, train=train, first_cls=first, fallback_cls=second,
                   date_text=date_text, date=date, name=name),
              {"status": "booked", "train_number": train, "travel_class": second},
              resolves(o, d) + [any_step("s1", [("check_availability", dict(train_number=train, date=date, travel_class=first)),
                                                ("book_ticket", first_args)]),
                                step("b2", "book_ticket", ba, ["r1", "r2", "s1"])], [booking_state(ba)])

def err_noroute(sid, o_text, d_text, date_text, text, window=None):
    o, d, date = code(o_text), code(d_text), DATES[date_text]
    kw = dict(origin=o, destination=d, date=date)
    if window: kw["depart_after"] = window
    assert run("search_trains", **kw)["count"] == 0
    return mk(sid, "ERR", "no_trains", text, dict(origin_text=o_text, dest_text=d_text, date_text=date_text, date=date),
              {"status": "no_option"}, resolves(o, d) + [step("s1", "search_trains", dict(origin=o, destination=d, date=date), ["r1", "r2"])])

def err_budget(sid, o_text, d_text, date_text, cls, max_fare, text):
    o, d, date = code(o_text), code(d_text), DATES[date_text]
    ts = [t for t in run("search_trains", origin=o, destination=d, date=date)["trains"] if cls in t["classes"]]
    assert len(ts) == 1; tr = ts[0]["train_number"]
    fare = run("get_fare", train_number=tr, origin=o, destination=d, travel_class=cls)["fare_per_passenger"]
    assert fare > max_fare
    return mk(sid, "ERR", "over_budget", text, dict(origin_text=o_text, dest_text=d_text, cls=cls, max_fare=max_fare, date=date),
              {"status": "no_option"},
              resolves(o, d) + [step("s1", "search_trains", dict(origin=o, destination=d, date=date), ["r1", "r2"]),
                                step("f1", "get_fare", dict(train_number=tr, origin=o, destination=d, travel_class=cls), ["s1"])],
              constraints=dict(origin=o, destination=d, date=date, classes=[cls], max_fare=max_fare))


# ---------------------------------------------------------------- UND: underspecified
def und(sid, text, missing, slots):
    return mk(sid, "UND", "missing_" + "_".join(missing), text, slots,
              {"status": "needs_clarification", "missing_info": missing}, [])


# ---------------------------------------------------------------- the 40 tasks
def build_all():
    T = []
    # L1 (8)
    T += [l1_resolve("L1-01", "Baroda", "What is the station code for {place}?"),
          l1_resolve("L1-02", "Madras", "Which station code does {place} use in this system?"),
          l1_avail("L1-03", "90101", "SL", "tomorrow", "How many {cls} seats are left on train {train} {date}?"),
          l1_avail("L1-04", "90206", "2A", "the day after tomorrow", "How many {cls} seats are available on train {train} {date}?"),
          l1_fare("L1-05", "90202", "NDLS", "JP", "3A", "What is the {cls} fare per passenger on train {train} from {o} to {d}?"),
          l1_fare("L1-06", "90302", "SBC", "SC", "2A", "Tell me the {cls} fare on train {train} between {o} and {d}."),
          l1_details("L1-07", "90204", "arr", "At what time does train {train} reach its final stop?"),
          l1_details("L1-08", "90102", "dep", "At what time does train {train} start its journey?")]
    # L2 (8)
    T += [l2_pick("L2-01", "Mumbai", "Ahmedabad", "tomorrow", False, "Which is the earliest train from {o} to {d} {date}?"),
          l2_pick("L2-02", "Ahmedabad", "Mumbai", "the day after tomorrow", True, "Which is the last train of the day from {o} to {d} {date}?"),
          l2_pick("L2-03", "Delhi", "Jaipur", "on 15 October", False, "Which train leaves earliest from {o} to {d} {date}?"),
          l2_seats("L2-04", "Bhopal", "Delhi", "2A", "tomorrow", "How many {cls} seats are available on the train from {o} to {d} {date}?"),
          l2_fare("L2-05", "Mumbai", "Ahmedabad", "90108", "3A", "What is the {cls} fare from {o} to {d} on train {train}?"),
          l2_book("L2-06", "Ahmedabad", "Surat", "90104", "SL", "tomorrow", "Ravi Mehta", 1, "Book {t} in {cls} on train {train} from {o} to {d} {date} in the name of {name}."),
          l2_book("L2-07", "Mumbai", "Pune", "90106", "CC", "the day after tomorrow", "Neha Kulkarni", 2, "Book {t} in {cls} on train {train} from {o} to {d} {date} in the name of {name}."),
          l2_book("L2-08", "Bengaluru", "Hyderabad", "90302", "3A", "on 15 October", "Imran Sheikh", 1, "Book {t} in {cls} on train {train} from {o} to {d} {date} in the name of {name}.")]
    # L3 (10)
    T += [l3("L3-01", "Mumbai", "Ahmedabad", "tomorrow", {"3A"}, "Find me a train from Mumbai to Ahmedabad tomorrow, leaving after 6 PM, with 3AC seats available.", after="18:00", check_seats=True),
          l3("L3-02", "Jaipur", "Delhi", "tomorrow", {"2A"}, "I need a train from Jaipur to Delhi tomorrow after 3 PM with 2AC seats available.", after="15:00", check_seats=True),
          l3("L3-03", "Delhi", "Jaipur", "tomorrow", {"3A"}, "Is there a train from Delhi to Jaipur tomorrow after noon with 3AC seats? Tell me which one.", after="12:00", check_seats=True),
          l3("L3-04", "Mumbai", "Ahmedabad", "the day after tomorrow", {"2A"}, "Book a 2AC ticket for Priya Shah from Mumbai to Ahmedabad the day after tomorrow on a train that leaves before 4 PM.", before="16:00", book=dict(name="Priya Shah", n=1)),
          l3("L3-05", "Ahmedabad", "Mumbai", "tomorrow", {"3A"}, "Find a train from Ahmedabad that gets me to Mumbai before 3 PM tomorrow, with 3AC seats available.", arrive_before="15:00", check_seats=True),
          l3("L3-06", "Mumbai", "Ahmedabad", "on 15 October", {"SL"}, "Book 2 sleeper tickets in the name of Karan Joshi from Mumbai to Ahmedabad on 15 October, on a train that reaches Ahmedabad before 2 PM.", arrive_before="14:00", book=dict(name="Karan Joshi", n=2)),
          l3("L3-07", "Delhi", "Jaipur", "the day after tomorrow", {"CC", "2A"}, "Find me a seat from Delhi to Jaipur the day after tomorrow, in chair car or 2AC, leaving before 8 AM and costing no more than \u20b9500 per person.", before="08:00", max_fare=500, check_fare=True),
          l3("L3-08", "Surat", "Ahmedabad", "tomorrow", {"1A"}, "I want a first AC seat from Surat to Ahmedabad tomorrow, leaving after 8 PM. Which train should I take?", after="20:00", check_seats=True),
          l3("L3-09", "Hyderabad", "Bengaluru", "tomorrow", {"CC"}, "Book one chair car ticket for Divya Reddy from Hyderabad to Bengaluru tomorrow, on a train leaving before noon.", before="12:00", book=dict(name="Divya Reddy", n=1)),
          l3("L3-10", "Pune", "Mumbai", "tomorrow", {"3A"}, "Is there a train from Pune to Mumbai tomorrow after 4 PM with 3AC seats? Tell me which one.", after="16:00", check_seats=True)]
    # ERR (8)
    T += [err_attempt("ERR-01", "90103", "3A", "Mumbai", "Ahmedabad", "tomorrow", "Anil Kapoor", "Book a 3AC ticket on train 90103 from Mumbai to Ahmedabad tomorrow for Anil Kapoor.", "sold_out"),
          err_attempt("ERR-02", "90204", "3A", "Jaipur", "Delhi", "tomorrow", "Meera Iyer", "Book a 3AC ticket on train 90204 from Jaipur to Delhi tomorrow for Meera Iyer.", "sold_out"),
          err_fallback("ERR-03", "90103", "3A", "2A", "Mumbai", "Ahmedabad", "tomorrow", "Suresh Nair", "Book a 3AC ticket on train 90103 from Mumbai to Ahmedabad tomorrow for Suresh Nair. If 3AC is full, book 2AC on the same train instead."),
          err_noroute("ERR-04", "Pune", "Jaipur", "tomorrow", "Are there any trains from Pune to Jaipur tomorrow?"),
          err_noroute("ERR-05", "Chennai", "Hyderabad", "tomorrow", "Book a chair car ticket from Chennai to Hyderabad tomorrow for Lakshmi Narayanan."),
          err_attempt("ERR-06", "90106", "2A", "Mumbai", "Pune", "tomorrow", "Rohit Desai", "Book a 2AC ticket on train 90106 from Mumbai to Pune tomorrow for Rohit Desai.", "class_not_offered"),
          err_budget("ERR-07", "Delhi", "Jaipur", "tomorrow", "CC", 400, "Find a chair car seat from Delhi to Jaipur tomorrow that costs under \u20b9400."),
          err_noroute("ERR-08", "Mumbai", "Ahmedabad", "tomorrow", "Is there a train from Mumbai to Ahmedabad leaving after 10 PM tomorrow?", window="22:00")]
    # UND (6)
    T += [und("UND-01", "Book a 3AC ticket from Mumbai to Ahmedabad for Rahul Verma.", ["date"], dict(name="Rahul Verma")),
          und("UND-02", "Show me trains from Delhi to Jaipur.", ["date"], {}),
          und("UND-03", "Book a ticket from Pune to Mumbai tomorrow for Sneha Patil.", ["travel_class"], dict(name="Sneha Patil", date="2026-10-11")),
          und("UND-04", "Book a 3AC ticket from Hyderabad to Bengaluru tomorrow.", ["passenger_name"], dict(date="2026-10-11")),
          und("UND-05", "Book a 3AC ticket to Jaipur tomorrow for Amit Singh.", ["origin"], dict(name="Amit Singh", date="2026-10-11")),
          und("UND-06", "How many seats are left on train 90101?", ["date", "travel_class"], {})]
    return T


def main():
    tasks = build_all()
    for t in tasks:
        probs = validate_task(t); assert not probs, (t.semantic_id, probs)
    os.makedirs("data", exist_ok=True)
    write_jsonl(tasks, "data/semantic_tasks.jsonl")
    from collections import Counter
    print(len(tasks), "tasks", dict(Counter(t.category for t in tasks)))


if __name__ == "__main__":
    main()
