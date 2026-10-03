"""Deterministic simulated railway environment + six tools (stdlib only).

Contract: Environment.call(tool_name, args_dict) -> result dict.
  success: {"status": "ok", ...}
  failure: {"status": "error", "error_code": "...", "message": "..."}
It NEVER raises on bad model input; bad input becomes an error observation,
because the agent is supposed to see it and recover.
"""
import datetime
import re
from copy import deepcopy

from .data import (MAX_ADVANCE_DAYS, RATE_X10, STATIONS, TODAY, TRAINS)

VALID_CLASSES = list(RATE_X10)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# ---- Single source of truth for tool schemas (also used to validate calls) ----
TOOL_SPECS = {
    "resolve_station": dict(
        description="Resolve a place or station name (any spelling the user used) "
                    "to a canonical station code. Use this before any tool that "
                    "needs a station code.",
        properties={"query": ("string", "Place or station name as written by the user")},
        required=["query"]),
    "search_trains": dict(
        description="Search trains running from origin to destination on a date, "
                    "optionally within a departure-time window at the origin. "
                    "Origin and destination must be station codes.",
        properties={"origin": ("string", "Origin station code"),
                    "destination": ("string", "Destination station code"),
                    "date": ("string", "Travel date, YYYY-MM-DD"),
                    "depart_after": ("string", "Earliest departure HH:MM (24h). Default 00:00"),
                    "depart_before": ("string", "Latest departure HH:MM (24h). Default 23:59")},
        required=["origin", "destination", "date"]),
    "get_train_details": dict(
        description="Get the stops, times, and travel classes of a train.",
        properties={"train_number": ("string", "5-digit train number")},
        required=["train_number"]),
    "check_availability": dict(
        description="Check how many seats are currently available in a class of a train on a date.",
        properties={"train_number": ("string", "5-digit train number"),
                    "date": ("string", "Travel date, YYYY-MM-DD"),
                    "travel_class": ("string", "One of SL, CC, 3A, 2A, 1A")},
        required=["train_number", "date", "travel_class"]),
    "get_fare": dict(
        description="Get the fare per passenger (rupees) for a class between two stops of a train.",
        properties={"train_number": ("string", "5-digit train number"),
                    "origin": ("string", "Boarding station code"),
                    "destination": ("string", "Destination station code"),
                    "travel_class": ("string", "One of SL, CC, 3A, 2A, 1A")},
        required=["train_number", "origin", "destination", "travel_class"]),
    "book_ticket": dict(
        description="Book a ticket. STATE-CHANGING: reduces seat availability and "
                    "creates a booking. Only call when the user has asked to book.",
        properties={"train_number": ("string", "5-digit train number"),
                    "date": ("string", "Travel date, YYYY-MM-DD"),
                    "origin": ("string", "Boarding station code"),
                    "destination": ("string", "Destination station code"),
                    "travel_class": ("string", "One of SL, CC, 3A, 2A, 1A"),
                    "passenger_name": ("string", "Full name of the passenger"),
                    "num_passengers": ("integer", "Number of passengers, 1-6. Default 1")},
        required=["train_number", "date", "origin", "destination",
                  "travel_class", "passenger_name"]),
}


def tool_specs():
    """Provider-neutral tool list: [{name, description, parameters(JSON schema)}]."""
    out = []
    for name, s in TOOL_SPECS.items():
        props = {k: {"type": t, "description": d} for k, (t, d) in s["properties"].items()}
        out.append({"name": name, "description": s["description"],
                    "parameters": {"type": "object", "properties": props,
                                   "required": s["required"],
                                   "additionalProperties": False}})
    return out


def _err(code, message):
    return {"status": "error", "error_code": code, "message": message}


def normalise_text(s):
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


# alias -> code (checked for uniqueness in tests)
_ALIAS = {}
for _code, (_name, _aliases) in STATIONS.items():
    for _a in _aliases + [_name]:
        _ALIAS[normalise_text(_a)] = _code


class Environment:
    def __init__(self):
        self._trains = {t["number"]: t for t in TRAINS}
        self.reset()

    # ---------- state ----------
    def reset(self):
        """Restore the fixed baseline state. Called before EVERY benchmark task."""
        self.seats = {(t["number"], c): n for t in TRAINS for c, n in t["classes"].items()}
        self.bookings = []

    def snapshot(self):
        """JSON-friendly copy of the mutable state, for scoring."""
        return {"bookings": deepcopy(self.bookings),
                "seats": {f"{t}|{c}": n for (t, c), n in sorted(self.seats.items())}}

    # ---------- dispatch ----------
    def call(self, name, args):
        spec = TOOL_SPECS.get(name)
        if spec is None:
            return _err("UNKNOWN_TOOL", f"No tool named '{name}'. Available: {sorted(TOOL_SPECS)}")
        if not isinstance(args, dict):
            return _err("INVALID_ARGUMENTS", "Arguments must be a JSON object.")
        extra = sorted(set(args) - set(spec["properties"]))
        if extra:
            return _err("INVALID_ARGUMENTS", f"Unexpected argument(s): {extra}")
        missing = [r for r in spec["required"] if r not in args]
        if missing:
            return _err("INVALID_ARGUMENTS", f"Missing required argument(s): {missing}")
        for k, v in args.items():
            want = spec["properties"][k][0]
            if want == "string" and not isinstance(v, str):
                return _err("INVALID_ARGUMENTS", f"'{k}' must be a string.")
            if want == "integer" and (isinstance(v, bool) or not isinstance(v, int)):
                return _err("INVALID_ARGUMENTS", f"'{k}' must be an integer.")
        return getattr(self, "_" + name)(**args)

    # ---------- validation helpers (return (value, None) or (None, error)) ----------
    def _station(self, s):
        code = s.strip().upper()
        if code in STATIONS:
            return code, None
        return None, _err("STATION_NOT_FOUND",
                          f"'{s}' is not a station code. Use resolve_station to get one.")

    def _train(self, n):
        t = self._trains.get(n.strip())
        if t is None:
            return None, _err("TRAIN_NOT_FOUND", f"No train numbered '{n}'.")
        return t, None

    def _date(self, s):
        if not _DATE_RE.match(s):
            return None, _err("INVALID_DATE", f"Date '{s}' must be in YYYY-MM-DD format.")
        try:
            d = datetime.date.fromisoformat(s)
        except ValueError:
            return None, _err("INVALID_DATE", f"'{s}' is not a real calendar date.")
        today = datetime.date.fromisoformat(TODAY)
        if d < today:
            return None, _err("INVALID_DATE", f"{s} is in the past (today is {TODAY}).")
        if d > today + datetime.timedelta(days=MAX_ADVANCE_DAYS):
            return None, _err("INVALID_DATE", f"{s} is beyond the {MAX_ADVANCE_DAYS}-day booking window.")
        return s, None

    def _class(self, train, c):
        c = c.strip().upper()
        if c not in VALID_CLASSES:
            return None, _err("INVALID_CLASS", f"'{c}' is not a class code. Valid: {VALID_CLASSES}")
        if c not in train["classes"]:
            return None, _err("INVALID_CLASS",
                              f"Train {train['number']} has no {c} class. "
                              f"Offered: {sorted(train['classes'])}")
        return c, None

    @staticmethod
    def _segment(train, o, d):
        """(origin_stop, dest_stop) if train goes o -> d in that order, else None."""
        codes = [s[0] for s in train["stops"]]
        if o in codes and d in codes and codes.index(o) < codes.index(d):
            return train["stops"][codes.index(o)], train["stops"][codes.index(d)]
        return None

    # ---------- the six tools ----------
    def _resolve_station(self, query):
        code = _ALIAS.get(normalise_text(query))
        if code is None:
            return _err("STATION_NOT_FOUND", f"Could not resolve '{query}' to a known station.")
        return {"status": "ok", "station_code": code, "station_name": STATIONS[code][0]}

    def _search_trains(self, origin, destination, date, depart_after="00:00", depart_before="23:59"):
        o, e = self._station(origin)
        if e: return e
        d, e = self._station(destination)
        if e: return e
        if o == d:
            return _err("INVALID_ROUTE", "Origin and destination are the same station.")
        _, e = self._date(date)
        if e: return e
        for t in (depart_after, depart_before):
            if not _TIME_RE.match(t):
                return _err("INVALID_TIME", f"Time '{t}' must be HH:MM (24h).")
        found = []
        for t in TRAINS:
            seg = self._segment(t, o, d)
            if seg and depart_after <= seg[0][2] <= depart_before:
                found.append({"train_number": t["number"], "train_name": t["name"],
                              "departure": seg[0][2], "arrival": seg[1][1],
                              "classes": sorted(t["classes"])})
        found.sort(key=lambda x: (x["departure"], x["train_number"]))
        return {"status": "ok", "origin": o, "destination": d, "date": date,
                "count": len(found), "trains": found}

    def _get_train_details(self, train_number):
        t, e = self._train(train_number)
        if e: return e
        stops = [{"station": s[0], "arrival": s[1], "departure": s[2], "km": s[3]}
                 for s in t["stops"]]
        return {"status": "ok", "train_number": t["number"], "train_name": t["name"],
                "stops": stops, "classes": sorted(t["classes"])}

    def _check_availability(self, train_number, date, travel_class):
        t, e = self._train(train_number)
        if e: return e
        _, e = self._date(date)
        if e: return e
        c, e = self._class(t, travel_class)
        if e: return e
        return {"status": "ok", "train_number": t["number"], "date": date,
                "travel_class": c, "seats_available": self.seats[(t["number"], c)]}

    def _fare_per_passenger(self, t, o, d, c):
        seg = self._segment(t, o, d)
        return None if seg is None else (RATE_X10[c] * (seg[1][3] - seg[0][3]) + 5) // 10

    def _get_fare(self, train_number, origin, destination, travel_class):
        t, e = self._train(train_number)
        if e: return e
        o, e = self._station(origin)
        if e: return e
        d, e = self._station(destination)
        if e: return e
        c, e = self._class(t, travel_class)
        if e: return e
        fare = self._fare_per_passenger(t, o, d, c)
        if fare is None:
            return _err("INVALID_ROUTE", f"Train {t['number']} does not run {o} -> {d}.")
        return {"status": "ok", "train_number": t["number"], "origin": o, "destination": d,
                "travel_class": c, "fare_per_passenger": fare, "currency": "INR"}

    def _book_ticket(self, train_number, date, origin, destination, travel_class,
                     passenger_name, num_passengers=1):
        t, e = self._train(train_number)
        if e: return e
        _, e = self._date(date)
        if e: return e
        o, e = self._station(origin)
        if e: return e
        d, e = self._station(destination)
        if e: return e
        c, e = self._class(t, travel_class)
        if e: return e
        fare = self._fare_per_passenger(t, o, d, c)
        if fare is None:
            return _err("INVALID_ROUTE", f"Train {t['number']} does not run {o} -> {d}.")
        if not passenger_name.strip():
            return _err("INVALID_PASSENGER", "passenger_name must not be empty.")
        if not 1 <= num_passengers <= 6:
            return _err("INVALID_PASSENGERS", "num_passengers must be between 1 and 6.")
        left = self.seats[(t["number"], c)]
        if left < num_passengers:
            return _err("SOLD_OUT", f"Only {left} seat(s) left in {c} on train {t['number']}.")
        self.seats[(t["number"], c)] = left - num_passengers
        booking = {"booking_id": f"PNR{len(self.bookings) + 1:04d}",
                   "train_number": t["number"], "date": date, "origin": o,
                   "destination": d, "travel_class": c,
                   "passenger_name": passenger_name.strip(),
                   "num_passengers": num_passengers,
                   "total_fare": fare * num_passengers}
        self.bookings.append(booking)
        return {"status": "ok", **booking}
