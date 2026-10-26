local _, ns = ...

-- Loaded last: wires events to the modules defined in the other files.

-- 2: adds installId, and adjustments carry `p` (when the character was last
-- seen on this computer). Older data simply lacks both; nothing is rewritten.
local DB_VERSION = 2

local frame = CreateFrame("Frame")

-- Identifies this copy of the SavedVariables. The companion merges ledgers from
-- several computers, and each numbers its transactions independently, so it
-- needs to know which computer a ledger came from.
local function newInstallId()
  return string.format("%x-%04x", GetServerTime(), math.random(0, 0xffff))
end

local function initDB()
  MariposaDB = MariposaDB or {}
  local db = MariposaDB
  db.version = db.version or DB_VERSION
  db.installId = db.installId or newInstallId()  -- v1 -> v2: the only migration step
  if db.version < DB_VERSION then db.version = DB_VERSION end
  db.settings = db.settings or { debug = false }
  db.chars = db.chars or {}
  db.warband = db.warband or {}
  ns.db = db

  local key = UnitName("player") .. "-" .. GetNormalizedRealmName()
  local c = db.chars[key] or { seq = 0, tx = {} }
  db.chars[key] = c
  c.name = UnitName("player")
  c.realm = GetRealmName()
  c.class = select(2, UnitClass("player"))
  c.faction = UnitFactionGroup("player")
  c.level = UnitLevel("player")
  ns.char, ns.charKey = c, key

  ns.ownChars = {}
  for k in pairs(db.chars) do
    ns.ownChars[ns.CanonicalName(k)] = k
  end
end

local function canViewAccountBank()
  -- CanViewBank reports whether the account bank is currently loaded. Looked up
  -- defensively so a missing API on older clients doesn't error.
  if C_Bank.CanViewBank then
    local ok, can = pcall(C_Bank.CanViewBank, Enum.BankType.Account)
    if ok then return can end
  end
  return false
end

local function snapshotWarband()
  if not (C_Bank and C_Bank.FetchDepositedMoney and Enum.BankType and Enum.BankType.Account) then return end
  local gold = C_Bank.FetchDepositedMoney(Enum.BankType.Account)
  if not gold then return end
  -- FetchDepositedMoney only returns a live figure while the account bank is
  -- loaded (at a banker). Elsewhere -- notably at logout -- it reports 0, which
  -- must not clobber the balance captured at the bank. A 0 is only trusted when
  -- the bank is actually viewable, i.e. a genuinely empty warband bank.
  if gold == 0 and not canViewAccountBank() then return end
  ns.db.warband.gold = gold
  ns.db.warband.updated = GetServerTime()
end

local handlers = {}

function handlers.PLAYER_LOGIN()
  initDB()
  local money = GetMoney()
  local c = ns.char
  if c.gold and c.gold ~= money then
    -- Gold moved while we weren't watching (addon disabled, a crash lost the
    -- last session's SavedVariables, or the character was played on another
    -- computer). Book it so balances reconcile, noting when this computer last
    -- saw the character: the companion drops whatever part of the adjustment
    -- another computer's ledger explains for that gap.
    local tx = ns.Ledger:Record("adjustment", money - c.gold)
    if tx then tx.p = c.lastSeen end
  end
  c.gold = money
  c.lastSeen = GetServerTime()
  ns.lastMoney = money
  ns.sessionStart = GetServerTime()
  snapshotWarband()
end

function handlers.PLAYER_MONEY()
  if not ns.lastMoney then return end
  local money = GetMoney()
  local delta = money - ns.lastMoney
  ns.lastMoney = money
  ns.char.gold = money
  ns.char.lastSeen = GetServerTime()
  if delta ~= 0 then ns.Ledger:AddDelta(delta) end
end

function handlers.QUEST_TURNED_IN(questID, _, moneyReward)
  if not moneyReward or moneyReward <= 0 then return end
  local cat = "quest"
  if C_QuestLog.IsWorldQuest(questID) then
    cat = "world_quest"
  elseif C_QuestLog.IsQuestTask(questID) then
    cat = "bonus"
  end
  ns.Ledger:Expect(cat, moneyReward, questID)
end

function handlers.PLAYER_INTERACTION_MANAGER_FRAME_SHOW(interactionType)
  ns.Context:OnInteraction(interactionType, true)
end

function handlers.PLAYER_INTERACTION_MANAGER_FRAME_HIDE(interactionType)
  ns.Context:OnInteraction(interactionType, false)
end

handlers.ACCOUNT_MONEY = snapshotWarband

function handlers.PLAYER_LOGOUT()
  -- The flush timer won't fire after logout; settle pending money now.
  ns.Ledger:Flush()
  -- GetMoney() can return 0 during logout. ns.char.gold is already kept current
  -- by PLAYER_LOGIN and every PLAYER_MONEY, so a 0 here is a bad read, not a
  -- real balance. Letting it overwrite would zero the saved balance and make the
  -- next login re-book the whole amount as an "adjustment". A genuine empty
  -- wallet was already recorded as 0 by PLAYER_MONEY, so skipping the update is
  -- safe. Only trust a non-zero final read.
  local money = GetMoney()
  if money and money > 0 then ns.char.gold = money end
  ns.char.lastSeen = GetServerTime()
  snapshotWarband()
end

for event, ctx in pairs(ns.Context.openEvents) do
  handlers[event] = function() ns.Context:Open(ctx) end
end
for event, ctx in pairs(ns.Context.closeEvents) do
  handlers[event] = function() ns.Context:Close(ctx) end
end

for event in pairs(handlers) do
  -- Registering an event the client doesn't know is an error; skip those.
  if not C_EventUtils.IsEventValid or C_EventUtils.IsEventValid(event) then
    frame:RegisterEvent(event)
  end
end

frame:SetScript("OnEvent", function(_, event, ...)
  handlers[event](...)
end)
