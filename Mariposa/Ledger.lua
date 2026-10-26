local _, ns = ...

-- Turns raw PLAYER_MONEY deltas into categorized transactions.
--
-- Hooks and events announce money they know is coming ("expectations"); the
-- delta is matched against those first, and anything left over is attributed
-- by whichever window is open (see Context.lua).
local Ledger = {}
ns.Ledger = Ledger

local FLUSH_DELAY = 0.3 -- money changes landing within this window are attributed together
local EXPECT_TTL = 3    -- seconds an expectation waits for its money to arrive

local pending = 0
local flushScheduled = false
local expectations = {}

local function sign(n)
  return n > 0 and 1 or (n < 0 and -1 or 0)
end

-- Returns the recorded transaction, so callers can attach extra fields.
function Ledger:Record(cat, amount, ref)
  if amount == 0 then return end
  local c = ns.char
  c.seq = c.seq + 1
  local tx = {
    s = c.seq,
    t = GetServerTime(),
    a = amount,
    k = cat,
    r = ref,
    m = C_Map.GetBestMapForUnit("player"),
  }
  c.tx[#c.tx + 1] = tx
  if ns.db.settings.debug then
    ns.Print(ns.FormatMoney(amount, true), ns.CategoryLabel(cat), ref and ("(" .. tostring(ref) .. ")") or "")
  end
  return tx
end

-- amount may be nil to claim whatever next arrives in direction `dir`
-- (e.g. a repair or AH deposit whose cost we can't read up front).
-- ttl overrides EXPECT_TTL: a claim that might never be paid (a bag with no
-- gold in it) should expire quickly so it can't capture unrelated money.
function Ledger:Expect(cat, amount, ref, dir, ttl)
  if amount == 0 then return end
  expectations[#expectations + 1] = {
    cat = cat,
    amount = amount,
    dir = amount and sign(amount) or dir,
    ref = ref,
    at = GetTime(),
    ttl = ttl,
  }
end

function Ledger:AddDelta(delta)
  pending = pending + delta
  if not flushScheduled then
    flushScheduled = true
    C_Timer.After(FLUSH_DELAY, function() Ledger:Flush() end)
  end
end

function Ledger:Flush()
  flushScheduled = false
  local remaining = pending
  pending = 0

  local now = GetTime()
  local live = {}
  for _, e in ipairs(expectations) do
    if now - e.at <= (e.ttl or EXPECT_TTL) then live[#live + 1] = e end
  end

  -- Exact amounts first, so a quest reward is split out of a combined delta.
  -- An expectation can be paid off across several deltas.
  for _, e in ipairs(live) do
    if remaining ~= 0 and e.amount and sign(e.amount) == sign(remaining) then
      local take = sign(remaining) * math.min(math.abs(e.amount), math.abs(remaining))
      self:Record(e.cat, take, e.ref)
      remaining = remaining - take
      e.amount = e.amount - take
      e.done = e.amount == 0
    end
  end

  -- Then open-ended claims take whatever is left in their direction.
  for _, e in ipairs(live) do
    if remaining ~= 0 and not e.amount and e.dir == sign(remaining) then
      self:Record(e.cat, remaining, e.ref)
      remaining = 0
      e.done = true
    end
  end

  expectations = {}
  for _, e in ipairs(live) do
    if not e.done then expectations[#expectations + 1] = e end
  end

  if remaining ~= 0 then
    self:Record(ns.Context:Resolve(remaining) or "other", remaining)
  end
end

-- Totals by category for transactions at or after `since`, optionally for a
-- single character. Ledgers are append-only, so we walk back and stop early.
function Ledger:Summarize(since, onlyChar)
  local totals = {}
  for key, c in pairs(ns.db.chars) do
    if not onlyChar or key == onlyChar then
      for i = #c.tx, 1, -1 do
        local tx = c.tx[i]
        if tx.t < since then break end
        totals[tx.k] = (totals[tx.k] or 0) + tx.a
      end
    end
  end
  return totals
end
