"""Render mariposa.db as one self-contained, offline HTML dashboard."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

TEMPLATE = Path(__file__).with_name("dashboard_template.html")
PLACEHOLDER = "/*__MARIPOSA_DATA__*/null"

# Mirrors the labels in Mariposa/Categories.lua.
CATEGORY_LABELS = {
    "quest": "Quests", "world_quest": "World Quests", "bonus": "Bonus Objectives",
    "loot": "Loot", "vendor_sell": "Vendor Sales", "vendor_buy": "Vendor Purchases",
    "repair": "Repairs", "ah_sale": "AH Sales", "ah_buy": "AH Purchases",
    "ah_deposit": "AH Deposits", "ah_refund": "AH Refunds", "mail_in": "Mail Received",
    "mail_out": "Mail Sent", "postage": "Postage", "cod": "COD Payments",
    "trade_in": "Trade Received", "trade_out": "Trade Given", "flight": "Flight Paths",
    "transmog": "Transmog", "barber": "Barber", "training": "Training",
    "guild_bank": "Guild Bank", "xfer_warband": "Warband Bank", "xfer_mail": "Mail to Alts",
    "adjustment": "Untracked Change", "other": "Other",
}


def dashboard_data(conn: sqlite3.Connection, transfer_categories: set[str]) -> dict:
    """Everything the page needs, as "pockets" (characters plus one warband bank
    per account) and transactions against them.

    Warband deposits are only recorded on the character side, so each one is
    mirrored onto the warband pocket. Transfers then net to zero across all
    pockets, and any pocket's balance history is its current balance minus
    later transactions.
    """
    pockets, index = [], {}
    for key, account, name, realm, cls, gold in conn.execute(
            "SELECT char_key, account, name, realm, class, gold FROM characters ORDER BY gold DESC"):
        index[key] = len(pockets)
        pockets.append({"kind": "character", "key": key, "account": account, "name": name or key,
                        "realm": realm or "", "cls": cls, "gold": gold or 0})

    warbands = conn.execute("SELECT account, gold FROM warband ORDER BY account").fetchall()
    warband_index = {}
    for account, gold in warbands:
        warband_index[account] = len(pockets)
        pockets.append({"kind": "warband", "key": f"warband:{account}", "account": account,
                        "name": "Warband Bank" if len(warbands) == 1 else f"Warband Bank ({account})",
                        "realm": "", "cls": None, "gold": gold or 0})

    tx = []
    for key, account, ts, amount, category, ref in conn.execute(
            """SELECT t.char_key, c.account, t.ts, t.amount, t.category, t.ref
               FROM transactions t JOIN characters c USING (char_key)
               ORDER BY t.ts, t.char_key, t.seq"""):
        tx.append([index[key], ts, amount, category, ref])
        if category == "xfer_warband" and account in warband_index:
            tx.append([warband_index[account], ts, -amount, category, pockets[index[key]]["name"]])

    return {
        "generatedAt": int(time.time()),
        "pockets": pockets,
        "tx": tx,
        "labels": CATEGORY_LABELS,
        "transfers": sorted(transfer_categories),
    }


def render_dashboard(conn: sqlite3.Connection, out: Path, transfer_categories: set[str]) -> None:
    data = json.dumps(dashboard_data(conn, transfer_categories), separators=(",", ":"))
    # The JSON sits in a <script> block; escape "<" so a ref like "</script>"
    # can't end it early.
    data = data.replace("<", "\\u003c")
    html = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in html:
        raise ValueError(f"{TEMPLATE.name} is missing the data placeholder")
    out.write_text(html.replace(PLACEHOLDER, data), encoding="utf-8")
