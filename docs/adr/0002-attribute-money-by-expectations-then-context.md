# ADR-0002: Attribute money by expectations, then context

- **Status:** Accepted
- **Date:** 2026-10-25

## Context

WoW exposes gold changes only as a balance (`GetMoney()`) and a bare `PLAYER_MONEY` event.
To categorize a change we have to infer its cause. Some sources tell us the exact amount
ahead of or right after the change (quest rewards, mail invoices, bank deposits); others
only tell us which window was open.

## Decision

Batch deltas for 0.3 s, then match them against **expectations** registered by hooks and
events: exact amounts first (partially, if needed), then open-ended claims such as repairs.
Attribute any remainder by the **open interaction context**, and fall back to `other`.

## Alternatives considered

| Option | Why not |
|---|---|
| Parse `CHAT_MSG_MONEY` / system chat | Localized strings, misses most sources, and chat can be restricted in Midnight instanced content. |
| Context only (which window is open) | Can't separate a quest reward from loot landing at the same moment, or an AH sale from other mail. |
| Hook everything, no context fallback | Many costs (vendor buys, flights, transmog) aren't readable up front. |

## Consequences

Most gold gets precise categories, and the rest still gets a reasonable guess. Expectations
live for 3 s, so in rare cases a stale one claims an unrelated change. The batching delay
means `/mp` can lag a change by 0.3 s.
