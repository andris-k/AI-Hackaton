"""Insert generated test fixed assets into the local database.

Usage: python -m scripts.seed_fixed_assets [count] [--seed N]
"""

from __future__ import annotations

import argparse
import random
import uuid
from datetime import date, timedelta

from app.db import _get_or_create_fixed_asset_category_id, db_session, initialize_database

# category -> (item names, models/variants, unit value range, quantity range)
CATALOG: dict[str, tuple[list[str], list[str], tuple[int, int], tuple[int, int]]] = {
    "IT equipment": (
        ["Laptop", "Desktop PC", "Monitor", "Docking station", "Network switch", "Wi-Fi access point",
         "Server", "NAS storage", "UPS unit", "Firewall appliance"],
        ["Dell", "HP", "Lenovo", "Apple", "Cisco", "Ubiquiti", "Synology", "APC", "Fortinet"],
        (150, 6500), (1, 5),
    ),
    "Office equipment": (
        ["Laser printer", "Multifunction printer", "Projector", "Paper shredder", "Scanner",
         "Conference phone", "Label printer", "Laminator"],
        ["Canon", "Brother", "Epson", "Xerox", "Ricoh", "Poly", "Fellowes"],
        (80, 3200), (1, 4),
    ),
    "Furniture": (
        ["Office desk", "Height-adjustable desk", "Office chair", "Meeting table", "Bookshelf",
         "Filing cabinet", "Reception counter", "Sofa", "Storage locker"],
        ["oak", "white", "grey", "walnut", "black", "birch"],
        (60, 2400), (1, 20),
    ),
    "Vehicles": (
        ["Passenger car", "Cargo van", "Pickup truck", "Electric scooter", "Forklift", "Trailer"],
        ["Toyota", "Volkswagen", "Škoda", "Ford", "Renault", "Linde", "Tesla"],
        (2500, 68000), (1, 1),
    ),
    "Machinery": (
        ["CNC milling machine", "Lathe", "Air compressor", "Welding machine", "Hydraulic press",
         "Industrial drill", "Generator", "Pallet wrapper"],
        ["Bosch", "Makita", "Atlas Copco", "Lincoln Electric", "DMG Mori", "Haas"],
        (900, 85000), (1, 3),
    ),
    "Kitchen appliances": (
        ["Refrigerator", "Microwave oven", "Coffee machine", "Dishwasher", "Water dispenser", "Electric kettle"],
        ["Bosch", "Siemens", "Electrolux", "De'Longhi", "Samsung", "Jura"],
        (30, 2800), (1, 4),
    ),
    "Tools": (
        ["Cordless drill set", "Angle grinder", "Laser level", "Tool chest", "Ladder", "Pressure washer",
         "Circular saw"],
        ["Makita", "DeWalt", "Bosch", "Milwaukee", "Hilti", "Kärcher"],
        (40, 1800), (1, 10),
    ),
    "Mobile devices": (
        ["Smartphone", "Tablet", "Barcode scanner", "Rugged handheld", "Two-way radio"],
        ["Apple", "Samsung", "Zebra", "Honeywell", "Motorola"],
        (90, 1600), (1, 15),
    ),
    "Security equipment": (
        ["IP camera", "Access control reader", "Alarm panel", "Safe", "NVR recorder", "Fire extinguisher"],
        ["Hikvision", "Axis", "Bosch", "Paxton", "Chubbsafes"],
        (45, 4200), (1, 12),
    ),
    "Medical equipment": (
        ["First aid kit", "AED defibrillator", "Eye wash station", "Stretcher"],
        ["Philips", "Zoll", "Cederroth", "Ferno"],
        (40, 2600), (1, 6),
    ),
}

PEOPLE = [
    "Andris Kalniņš", "Jānis Bērziņš", "Ivars Ozols", "Juris Liepa", "Marta Krūmiņa", "Anna Kalniņa",
    "Laura Zariņa", "Pēteris Vītols", "Ilze Jansone", "Edgars Lācis", "Kristīne Siliņa", "Mārtiņš Eglītis",
    "Elīna Ābele", "Roberts Priede", "Santa Grīnberga",
]


def generate(count: int, rng: random.Random) -> list[tuple[str, str, int, float, str, str]]:
    """Return (category, name, quantity, unit value, responsible person, registration date) tuples."""
    start = date(2019, 1, 1)
    span_days = (date.today() - start).days
    categories = list(CATALOG)
    records = []
    for _ in range(count):
        category = rng.choice(categories)
        items, variants, (lo, hi), (qmin, qmax) = CATALOG[category]
        name = f"{rng.choice(items)} {rng.choice(variants)} #{rng.randint(100, 9999)}"
        # Skew values towards the low end, as real asset registers are.
        value = round(lo + (hi - lo) * rng.random() ** 2.2, 2)
        quantity = rng.randint(qmin, qmax)
        registered = start + timedelta(days=rng.randint(0, span_days))
        records.append((category, name, quantity, value, rng.choice(PEOPLE), registered.isoformat()))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("count", nargs="?", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=None, help="random seed for reproducible data")
    args = parser.parse_args()

    initialize_database()
    records = generate(args.count, random.Random(args.seed))
    with db_session() as connection:
        category_ids = {name: _get_or_create_fixed_asset_category_id(connection, name) for name in CATALOG}
        connection.executemany(
            """
            INSERT INTO fixed_assets (
                id, category_id, name, category, quantity, initial_value, responsible_person, registration_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (str(uuid.uuid4()), category_ids[cat], name, cat, qty, value, person, registered)
                for cat, name, qty, value, person, registered in records
            ],
        )
    print(f"Inserted {len(records)} fixed assets across {len(CATALOG)} categories.")


if __name__ == "__main__":
    main()
