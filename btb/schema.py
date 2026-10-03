"""Task + gold-label schema (stdlib dataclasses; plain JSON on disk).

A SemanticTask is language-independent: ONE gold label, shared by the English
and Hinglish surface forms. Language only changes the query text.

GOLD LABEL = three parts, all derived by running the fixed Environment:
  1. expected_answer   : fields the agent's structured final answer must match
  2. expected_bookings : the exact environment end-state (list of bookings, no booking_id)
  3. core_steps        : minimal sufficient tool calls + dependencies (NOT one rigid sequence)

core_steps format (a list of steps):
  {"id": "s1",
   "any_of": [ {"tool": "...", "args": {...}}, ... ],   # any ONE alternative satisfies the step
   "depends_on": ["r1", "r2"]}                           # steps whose result this step needs
  - Only the arguments listed in `args` are graded (optional args with defaults are filled in).
  - resolve_station uses {"resolves_to": "MMCT"}: graded by whether the agent's query
    resolves (via the environment's alias table) to that station code.
  - depends_on means: a matching call for this step must occur AFTER a matching call
    for each listed step. Steps with no dependency relation may happen in any order.
"""
import json
from dataclasses import asdict, dataclass, field

from .env import TOOL_SPECS

CATEGORIES = ("L1", "L2", "L3", "ERR", "UND")
STATUSES = ("answered", "booked", "no_option", "needs_clarification")

# Structured FINAL ANSWER the agent must output (JSON object). Only `status` is mandatory.
ANSWER_FIELDS = ("status", "train_number", "travel_class", "fare", "seats_available",
                 "booking_id", "station_code", "departure_time", "arrival_time",
                 "missing_info", "message")
# Subset that a gold label may constrain (booking_id is checked against env state instead)
GOLD_ANSWER_FIELDS = tuple(f for f in ANSWER_FIELDS if f not in ("booking_id", "message"))
MISSING_VOCAB = ("origin", "destination", "date", "travel_class", "passenger_name")


@dataclass
class Gold:
    expected_answer: dict
    expected_bookings: list = field(default_factory=list)
    core_steps: list = field(default_factory=list)

    @property
    def min_calls(self):
        return len(self.core_steps)


@dataclass
class SemanticTask:
    semantic_id: str
    category: str
    family: str
    english: str
    slots: dict
    constraints: dict
    gold: Gold
    hinglish: str = None          # human-authored in Stage 5; never auto-translated

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        d = dict(d)
        d["gold"] = Gold(**d["gold"])
        return SemanticTask(**d)


def validate_task(t):
    """Return a list of problems (empty list = valid)."""
    p = []
    g = t.gold
    if t.category not in CATEGORIES:
        p.append(f"bad category {t.category}")
    if not t.semantic_id.startswith(t.category + "-"):
        p.append("semantic_id must start with category")
    st = g.expected_answer.get("status")
    if st not in STATUSES:
        p.append(f"bad status {st}")
    for k in g.expected_answer:
        if k not in GOLD_ANSWER_FIELDS:
            p.append(f"expected_answer field not allowed: {k}")
    if (st == "booked") != (len(g.expected_bookings) > 0):
        p.append("status 'booked' must coincide with non-empty expected_bookings")
    ids = []
    for s in g.core_steps:
        if s["id"] in ids:
            p.append(f"duplicate step id {s['id']}")
        for d in s["depends_on"]:
            if d not in ids:
                p.append(f"step {s['id']} depends on unknown/later step {d}")
        ids.append(s["id"])
        if not s["any_of"]:
            p.append(f"step {s['id']} has no alternatives")
        for alt in s["any_of"]:
            tool, args = alt["tool"], alt["args"]
            if tool not in TOOL_SPECS:
                p.append(f"unknown tool {tool}")
            elif tool == "resolve_station":
                if set(args) != {"resolves_to"}:
                    p.append("resolve_station step must use {'resolves_to': CODE}")
            else:
                spec = TOOL_SPECS[tool]
                if not set(spec["required"]) <= set(args) <= set(spec["properties"]):
                    p.append(f"step {s['id']} bad args for {tool}: {sorted(args)}")
    if t.category == "UND":
        if g.core_steps or st != "needs_clarification":
            p.append("UND tasks: no core steps, status needs_clarification")
        if not set(g.expected_answer.get("missing_info", [])) <= set(MISSING_VOCAB) or \
           not g.expected_answer.get("missing_info"):
            p.append("UND tasks need missing_info drawn from MISSING_VOCAB")
    return p


def write_jsonl(tasks, path):
    with open(path, "w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [SemanticTask.from_dict(json.loads(line)) for line in f if line.strip()]
