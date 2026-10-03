"""Fixed world data for the simulated railway environment.

Everything here is FICTIONAL on purpose (train numbers, names, times, fares),
so a model cannot answer from memorised real-world IRCTC knowledge.
No runtime randomness anywhere: the world is fully defined by this file.
"""

TODAY = "2026-10-10"          # fixed "today" so that "tomorrow" is well-defined
MAX_ADVANCE_DAYS = 30         # bookable window: TODAY .. TODAY+30

# Fare rate in TENTHS of a rupee per km per passenger (integers => exact arithmetic).
# fare = (rate_x10 * km + 5) // 10   i.e. rupees, rounded HALF UP.
RATE_X10 = {"SL": 5, "CC": 14, "3A": 12, "2A": 17, "1A": 30}

# code -> (display name, aliases). Aliases are matched after normalisation
# (lowercase, punctuation removed, spaces collapsed). Roman script only.
STATIONS = {
    "MMCT": ("Mumbai Central",  ["mumbai", "bombay", "mumbai central", "mmct"]),
    "ST":   ("Surat",           ["surat", "st"]),
    "BRC":  ("Vadodara",        ["vadodara", "baroda", "brc"]),
    "ADI":  ("Ahmedabad",       ["ahmedabad", "amdavad", "adi"]),
    "PUNE": ("Pune",            ["pune", "poona"]),
    "NDLS": ("New Delhi",       ["delhi", "new delhi", "dilli", "ndls"]),
    "JP":   ("Jaipur",          ["jaipur", "jp"]),
    "BPL":  ("Bhopal",          ["bhopal", "bpl"]),
    "SC":   ("Hyderabad",       ["hyderabad", "secunderabad", "sc"]),
    "SBC":  ("Bengaluru",       ["bengaluru", "bangalore", "sbc"]),
    "MAS":  ("Chennai",         ["chennai", "madras", "mas"]),
}

# stop = (station_code, arrival, departure, km_from_origin); None = not applicable
# classes = {class_code: seats_available_at_reset}
# All times are same-day HH:MM (midsem simplification: no overnight trains).
TRAINS = [
    # ---- Western corridor ----
    dict(number="90101", name="Sagar Express",
         stops=[("MMCT", None, "06:10", 0), ("ST", "09:05", "09:10", 263),
                ("BRC", "11:05", "11:10", 392), ("ADI", "13:30", None, 491)],
         classes={"SL": 120, "3A": 40, "CC": 60}),
    dict(number="90102", name="Gujarat Link",
         stops=[("MMCT", None, "15:40", 0), ("ST", "18:40", "18:45", 263),
                ("BRC", "20:50", "20:55", 392), ("ADI", "22:55", None, 491)],
         classes={"SL": 90, "3A": 25, "2A": 12}),
    dict(number="90103", name="Saurashtra Superfast",
         stops=[("MMCT", None, "18:20", 0), ("ST", "20:55", "21:00", 263),
                ("BRC", "22:40", "22:45", 392), ("ADI", "23:55", None, 491)],
         classes={"3A": 0, "2A": 10, "1A": 4}),          # 3A sold out
    dict(number="90108", name="Kutch Night Express",
         stops=[("MMCT", None, "19:10", 0), ("ADI", "23:50", None, 491)],
         classes={"SL": 50, "3A": 18, "2A": 6}),
    dict(number="90104", name="Sabarmati Passenger",
         stops=[("ADI", None, "06:30", 0), ("BRC", "08:50", "08:55", 99),
                ("ST", "10:45", "10:50", 228), ("MMCT", "13:45", None, 491)],
         classes={"SL": 100, "3A": 35, "CC": 55}),
    dict(number="90105", name="Narmada Link",
         stops=[("ADI", None, "14:00", 0), ("BRC", "16:15", "16:20", 99),
                ("MMCT", "21:30", None, 491)],
         classes={"3A": 20, "2A": 9, "1A": 3}),
    dict(number="90106", name="Deccan Intercity",
         stops=[("MMCT", None, "07:00", 0), ("PUNE", "10:45", None, 192)],
         classes={"CC": 70, "3A": 30}),
    dict(number="90107", name="Sahyadri Intercity",
         stops=[("PUNE", None, "17:00", 0), ("MMCT", "20:40", None, 192)],
         classes={"CC": 60, "3A": 20}),
    # ---- Northern corridor ----
    dict(number="90201", name="Pink City Express",
         stops=[("NDLS", None, "06:00", 0), ("JP", "10:30", None, 308)],
         classes={"CC": 80, "2A": 20}),
    dict(number="90202", name="Aravali Mail",
         stops=[("NDLS", None, "16:30", 0), ("JP", "21:15", None, 308)],
         classes={"SL": 100, "3A": 35, "2A": 15}),
    dict(number="90203", name="Jaipur Day Express",
         stops=[("JP", None, "07:30", 0), ("NDLS", "12:10", None, 308)],
         classes={"CC": 70, "3A": 25}),
    dict(number="90204", name="Rajputana Evening",
         stops=[("JP", None, "18:00", 0), ("NDLS", "22:45", None, 308)],
         classes={"SL": 90, "3A": 0, "2A": 8, "1A": 3}),   # 3A sold out
    dict(number="90205", name="Malwa Express",
         stops=[("NDLS", None, "06:15", 0), ("BPL", "14:10", None, 705)],
         classes={"CC": 50, "2A": 14}),
    dict(number="90206", name="Vindhya Mail",
         stops=[("BPL", None, "15:00", 0), ("NDLS", "23:10", None, 705)],
         classes={"SL": 80, "3A": 22, "2A": 10}),
    # ---- Southern corridor ----
    dict(number="90301", name="Charminar Link",
         stops=[("SC", None, "06:00", 0), ("SBC", "14:30", None, 570)],
         classes={"CC": 60, "3A": 30}),
    dict(number="90302", name="Garden City Express",
         stops=[("SBC", None, "08:00", 0), ("SC", "17:00", None, 570)],
         classes={"SL": 90, "3A": 28, "2A": 10}),
    dict(number="90303", name="Coromandel Day Link",
         stops=[("SBC", None, "06:30", 0), ("MAS", "11:15", None, 347)],
         classes={"CC": 75, "3A": 25}),
]
