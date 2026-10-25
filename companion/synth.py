#!/usr/bin/env python3
"""Write a synthetic WTF folder with a believable Mariposa.lua, so the importer
and dashboard can be developed without playing.

    python3 companion/synth.py                         # -> synthetic/WTF
    python3 companion/synth.py --days 180 --seed 7 --out /tmp/WTF

Output is deterministic for a given --seed and --end.
"""
from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

G = 10000  # copper per gold
DAY = 86400

# key, name, realm, class, faction, level, starting gold, profile
CHARACTERS = [
    ("Aurelia-Area52", "Aurelia", "Area 52", "MAGE", "Horde", 90, 1_400_000, "trader"),
    ("Brannoc-Area52", "Brannoc", "Area 52", "WARRIOR", "Horde", 90, 260_000, "main"),
    ("Thistle-Area52", "Thistle", "Area 52", "DRUID", "Horde", 90, 85_000, "alt"),
    ("Vexis-Stormrage", "Vexis", "Stormrage", "ROGUE", "Alliance", 84, 9_000, "leveling"),
]
WARBAND_START = 600_000

# Chance of logging in on a given day; leveling only starts partway through.
PLAY_CHANCE = {"trader": 0.8, "main": 0.85, "alt": 0.45, "leveling": 0.5}

AH_ITEMS = [
    ("Mycobloom", 900, 4_000), ("Luredrop", 1_200, 5_500), ("Bismuth", 700, 3_000),
    ("Flask of Alchemical Chaos", 6_000, 22_000), ("Algari Mana Potion", 1_500, 7_000),
    ("Crystalline Powder", 2_000, 9_000), ("Ironclaw Ore", 800, 3_500),
    ("Charged Alloy", 3_000, 12_000), ("Shadowy Gem Cluster", 4_000, 18_000),
]
ZONES = [2248, 2214, 2215, 2255, 2339, 2369, 2395, 2405]
FRIENDS = ["Kaelynn-Area52", "Morrow-Area52", "Pippa-Stormrage"]


class World:
    """Generates events in time order and keeps every balance non-negative."""

    def __init__(self, rng: random.Random, end: int):
        self.rng = rng
        self.end = end
        self.gold = {c[0]: c[6] * G + rng.randrange(G) for c in CHARACTERS}
        self.start_gold = dict(self.gold)
        self.warband = WARBAND_START * G
        self.events: dict[str, list] = {c[0]: [] for c in CHARACTERS}

    def copper(self, lo: float, hi: float) -> int:
        return int(self.rng.uniform(lo, hi) * G) + self.rng.randrange(100)

    def add(self, char: str, t: int, amount: int, cat: str, ref=None, zone: int | None = None) -> bool:
        if t > self.end:
            return False
        if amount < 0 and self.gold[char] + amount < 0:
            return False
        if cat == "xfer_warband" and self.warband - amount < 0:
            return False
        self.gold[char] += amount
        if cat == "xfer_warband":
            self.warband -= amount
        tx = {"t": t, "a": amount, "k": cat}
        if ref is not None:
            tx["r"] = ref
        if zone is not None:
            tx["m"] = zone
        self.events[char].append(tx)
        return True


def play_session(w: World, char: str, profile: str, t: int) -> int:
    """Simulate one evening on a character; return the time it ended."""
    rng = w.rng
    zone = rng.choice(ZONES)

    def step(lo=20, hi=300):
        nonlocal t
        t += rng.randint(lo, hi)
        return t

    if profile == "trader":
        for _ in range(rng.randint(0, 5)):
            name, lo, hi = rng.choice(AH_ITEMS)
            w.add(char, step(), w.copper(lo, hi), "ah_sale", name)
        for _ in range(rng.randint(2, 8)):
            w.add(char, step(), -w.copper(15, 140), "ah_deposit")
        for _ in range(rng.randint(0, 4)):
            name, lo, hi = rng.choice(AH_ITEMS)
            w.add(char, step(), -w.copper(lo * 0.6, hi * 0.8), "ah_buy", name)
        if rng.random() < 0.25:
            w.add(char, step(), -w.copper(0.3, 0.3), "postage")
        if rng.random() < 0.12:
            # Both legs share a timestamp, so neither can fall past --end alone
            # and the alt never spends gold before it arrives.
            target = rng.choice(["Brannoc-Area52", "Thistle-Area52"])
            amount = w.copper(10_000, 60_000)
            if w.add(char, step(), -amount, "xfer_mail", target):
                w.add(target, t, amount, "xfer_mail", char.split("-")[0])
        if rng.random() < 0.1:
            w.add(char, step(), -w.copper(50_000, 250_000), "xfer_warband")
        return t

    leveling = profile == "leveling"
    wq_count = {"main": (3, 9), "alt": (1, 4), "leveling": (0, 1)}[profile]
    for _ in range(rng.randint(*wq_count)):
        w.add(char, step(120, 600), w.copper(250, 950), "world_quest", rng.randint(80000, 89999), zone)
    for _ in range(rng.randint(4, 12) if leveling else rng.randint(0, 2)):
        w.add(char, step(200, 700), w.copper(4, 45) if leveling else w.copper(40, 180),
              "quest", rng.randint(70000, 79999), zone)
    if rng.random() < 0.3:
        w.add(char, step(), w.copper(80, 300), "bonus", rng.randint(70000, 79999), zone)
    for _ in range(rng.randint(10, 45)):
        w.add(char, step(15, 90), w.copper(0.4, 22), "loot", None, zone)
    for _ in range(rng.randint(1, 3)):
        w.add(char, step(), w.copper(15, 320), "vendor_sell")
    if rng.random() < 0.3:
        w.add(char, step(), -w.copper(10, 480), "vendor_buy")
    if rng.random() < 0.65:
        w.add(char, step(), -w.copper(60, 420) if not leveling else -w.copper(5, 60), "repair")
    for _ in range(rng.randint(0, 3)):
        w.add(char, step(), -w.copper(1, 8), "flight")
    if rng.random() < 0.05:
        w.add(char, step(), -w.copper(50, 800), "transmog")
    if rng.random() < 0.01:
        w.add(char, step(), -w.copper(100, 3_000), "barber")
    if leveling and rng.random() < 0.15:
        w.add(char, step(), -w.copper(20, 200), "training")
    if leveling and rng.random() < 0.3:
        w.add(char, step(), w.copper(2_000, 10_000), "xfer_warband")
    if profile == "main" and rng.random() < 0.15:
        w.add(char, step(), -w.copper(20_000, 80_000), "xfer_warband")
    if profile == "main" and rng.random() < 0.05:
        w.add(char, step(), -w.copper(1_000, 5_000), "guild_bank")
    if rng.random() < 0.03:
        w.add(char, step(), w.copper(500, 5_000), "mail_in", rng.choice(FRIENDS))
    if rng.random() < 0.02:
        w.add(char, step(), -w.copper(500, 3_000), "trade_out")
    return t


def generate(days: int, seed: int, end: int) -> dict:
    rng = random.Random(seed)
    w = World(rng, end)
    first_day = end - end % DAY - (days - 1) * DAY
    for d in range(days):
        day = first_day + d * DAY
        weekend = time.gmtime(day).tm_wday >= 5
        evening = day + rng.randint(16, 21) * 3600 + rng.randrange(3600)
        for key, *_, profile in CHARACTERS:
            if profile == "leveling" and d < days * 0.6:
                continue
            if rng.random() < PLAY_CHANCE[profile] + (0.1 if weekend else 0):
                evening = play_session(w, key, profile, evening) + rng.randint(300, 1800)

    # One gap the addon couldn't see, to exercise the "Untracked Change" path.
    thistle = w.events["Thistle-Area52"]
    if thistle:
        w.add("Thistle-Area52", thistle[len(thistle) // 2]["t"] + 1, 1_234 * G, "adjustment")

    chars = {}
    for key, name, realm, cls, faction, level, *_ in CHARACTERS:
        txs = sorted(w.events[key], key=lambda tx: tx["t"])
        for seq, tx in enumerate(txs, 1):
            tx["s"] = seq
        chars[key] = {
            "name": name, "realm": realm, "class": cls, "faction": faction, "level": level,
            "gold": w.start_gold[key] + sum(tx["a"] for tx in txs),
            "lastSeen": txs[-1]["t"] if txs else end,
            "seq": len(txs), "tx": txs,
        }
    warband = WARBAND_START * G - sum(
        tx["a"] for c in chars.values() for tx in c["tx"] if tx["k"] == "xfer_warband")
    return {
        "version": 1,
        "settings": {"debug": False},
        "warband": {"gold": warband, "updated": end},
        "chars": chars,
    }


def to_lua(value, depth: int = 0) -> str:
    """Serialize like WoW's SavedVariables writer (tabs, bracketed keys, -- [n])."""
    pad = "\t" * depth
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(value, list):
        lines = ["{"]
        lines += [f"{pad}\t{to_lua(v, depth + 1)}, -- [{i}]" for i, v in enumerate(value, 1)]
        return "\n".join(lines + [pad + "}"])
    if isinstance(value, dict):
        lines = ["{"]
        for k, v in value.items():
            key = f'"{k}"' if isinstance(k, str) else str(k)
            lines.append(f"{pad}\t[{key}] = {to_lua(v, depth + 1)},")
        return "\n".join(lines + [pad + "}"])
    raise TypeError(f"can't serialize {type(value).__name__}")


def write_wtf(out: Path, db: dict, account: str = "SYNTHETIC") -> Path:
    path = out / "Account" / account / "SavedVariables" / "Mariposa.lua"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\nMariposaDB = " + to_lua(db) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("synthetic/WTF"), help="WTF folder to write")
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--end", type=int, default=int(time.time()), help="last timestamp (epoch); default now")
    args = ap.parse_args(argv)

    db = generate(args.days, args.seed, args.end)
    path = write_wtf(args.out, db)
    n = sum(len(c["tx"]) for c in db["chars"].values())
    print(f"wrote {n} transactions for {len(db['chars'])} characters to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
