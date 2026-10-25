local _, ns = ...

-- Loaded last: wires events to the modules defined in the other files.

local DB_VERSION = 1

local frame = CreateFrame("Frame")

local function initDB()
  MariposaDB = MariposaDB or {}
  local db = MariposaDB
  db.version = db.version or DB_VERSION
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

local function snapshotWarband()
  if not (C_Bank and C_Bank.FetchDepositedMoney and Enum.BankType and Enum.BankType.Account) then return end
  local gold = C_Bank.FetchDepositedMoney(Enum.BankType.Account)
  if gold then
    ns.db.warband.gold = gold
    ns.db.warband.updated = GetServerTime()
  end
end

local handlers = {}

function handlers.PLAYER_LOGIN()
  initDB()
  local money = GetMoney()
  local c = ns.char
  if c.gold and c.gold ~= money then
    -- Gold moved while we weren't watching (addon disabled, or a crash lost
    -- the last session's SavedVariables). Book it so balances reconcile.
    ns.Ledger:Record("adjustment", money - c.gold)
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
  ns.char.gold = GetMoney()
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
