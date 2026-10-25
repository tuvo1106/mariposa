# AGENTS.md

Working notes for anyone (human or AI) contributing to this repo — how to work in the code,
and why things are the way they are. `DESIGN.md`/`ARCHITECTURE.md` (if this project has one)
is the source of truth for *what* we're building; this file is *how*.

## Conventions

- Commit messages: [Conventional Commits](https://www.conventionalcommits.org/)
  (`type(scope): subject`); no `Co-Authored-By` trailer. Enforced by a
  `commit-msg` hook — run `lefthook install` once after cloning. See
  [CONTRIBUTING.md](CONTRIBUTING.md) for the full commit/PR/ADR process.
- **Never commit directly to `main`.** One PR per feature. Branch prefixes:
  `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`.
- **Build as if this repo were public.** No secrets, credentials, tokens, or
  real user data committed — ever, not "temporarily," not in a branch you plan
  to squash. Config comes from environment variables (`.env`, gitignored). A
  `no-secrets` pre-commit hook backs this up but isn't a substitute for not
  doing it in the first place.

## Working on Mariposa

- `DESIGN.md` is the spec; `docs/adr/0002` and `0003` explain the two load-bearing choices
  (how money is attributed, and why data leaves the game via SavedVariables).
- Addon files load in `.toc` order and share state through the addon namespace `ns`.
  `Core.lua` is last because it registers events against the other modules.
- Guard any API that might not exist (`if C_Bank and C_Bank.DepositMoney`); registering an
  unknown event or hooking a missing function breaks the whole addon on load.
- Amounts are always integer copper. Adding a category means touching
  `Mariposa/Categories.lua`, plus `TRANSFER_CATEGORIES` in `companion/mariposa.py` if it's
  a transfer.
- Changing the SavedVariables shape: bump `DB_VERSION` in `Core.lua`, migrate in `initDB`,
  and keep the importer reading both shapes.
- The companion stays standard-library-only Python 3.
