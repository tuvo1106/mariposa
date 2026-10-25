# ADR-0004: Dashboard as a generated static HTML file

- **Status:** Accepted
- **Date:** 2026-10-25

## Context

The ledger lives in `mariposa.db` (ADR-0003). The goal is an offline dashboard that's
quick to open after a play session, and the companion is standard-library-only Python.

## Decision

`mariposa.py --dashboard out.html` fills `companion/dashboard_template.html` with the data
as embedded JSON. The page draws its charts with hand-written SVG and plain JS, with no
external requests, so it works from `file://`.

## Alternatives considered

| Option | Why not |
|---|---|
| Streamlit | Adds a heavy dependency and a running server for what's a read-only view. |
| Grafana / Evidence.dev over SQLite | Good for exploration, but a separate install and service to keep running. |
| Chart library from a CDN | Breaks offline use; vendoring one adds a few hundred KB we don't need for four chart types. |
| Page reads `mariposa.db` in the browser (sql.js) | Needs a WASM bundle, and browsers can't open local files without a picker. |

## Consequences

Opening a dashboard is a double-click, and the file can be shared as-is. New chart types
are written by hand. All data is embedded, so the file grows with the ledger (about 1 MB
per 25k transactions); retention (roadmap 5) keeps that bounded.
