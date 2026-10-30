local _, ns = ...

-- Local midnight `daysAgo` days back. Calendar days, like the dashboard's
-- ranges; time() normalizes a negative day into the previous month.
local function startOfDay(daysAgo)
  local d = date("*t")
  d.day = d.day - (daysAgo or 0)
  d.hour, d.min, d.sec = 0, 0, 0
  return time(d)
end

local function byMagnitude(a, b)
  return math.abs(a[2]) > math.abs(b[2])
end

local function printSummary(title, totals, elapsed)
  local income, expense = {}, {}
  local incomeTotal, expenseTotal, transferTotal = 0, 0, 0
  for cat, amount in pairs(totals) do
    if ns.IsTransfer(cat) then
      transferTotal = transferTotal + amount
    elseif amount > 0 then
      income[#income + 1] = { cat, amount }
      incomeTotal = incomeTotal + amount
    elseif amount < 0 then
      expense[#expense + 1] = { cat, amount }
      expenseTotal = expenseTotal + amount
    end
  end
  table.sort(income, byMagnitude)
  table.sort(expense, byMagnitude)

  ns.Print("|cffffd100" .. title .. "|r")
  print("  Income " .. ns.FormatMoney(incomeTotal, true))
  for _, row in ipairs(income) do
    print("    " .. ns.CategoryLabel(row[1]) .. "  " .. ns.FormatMoney(row[2], true))
  end
  print("  Expenses " .. ns.FormatMoney(expenseTotal, true))
  for _, row in ipairs(expense) do
    print("    " .. ns.CategoryLabel(row[1]) .. "  " .. ns.FormatMoney(row[2], true))
  end
  if transferTotal ~= 0 then
    print("  Transfers " .. ns.FormatMoney(transferTotal, true) .. " |cff888888(not counted)|r")
  end

  local net = incomeTotal + expenseTotal
  local line = "  Net " .. ns.FormatMoney(net, true)
  if elapsed and elapsed >= 60 then
    line = line .. string.format("  |cff888888(%s/hr over %s)|r",
      ns.FormatMoney(math.floor(net * 3600 / elapsed)), SecondsToTime(elapsed))
  end
  print(line)
end

local commands = {}

function commands.session()
  printSummary("This session", ns.Ledger:Summarize(ns.sessionStart, ns.charKey),
    GetServerTime() - ns.sessionStart)
end

function commands.today()
  printSummary("Today, all characters", ns.Ledger:Summarize(startOfDay(0)))
end

function commands.week()
  printSummary("Last 7 days, all characters", ns.Ledger:Summarize(startOfDay(6)))
end

function commands.chars()
  local list, total, nameCount = {}, 0, {}
  for key, c in pairs(ns.db.chars) do
    list[#list + 1] = { key = key, c = c }
    total = total + (c.gold or 0)
    local n = c.name or key
    nameCount[n] = (nameCount[n] or 0) + 1
  end
  table.sort(list, function(a, b) return (a.c.gold or 0) > (b.c.gold or 0) end)

  ns.Print("|cffffd100Net worth|r")
  for _, row in ipairs(list) do
    -- The name alone, plus the realm only when two characters share a name.
    local label = row.c.name or row.key
    if nameCount[label] > 1 and row.c.realm then label = label .. " (" .. row.c.realm .. ")" end
    local color = row.c.class and C_ClassColor.GetClassColor(row.c.class)
    local name = color and color:WrapTextInColorCode(label) or label
    print("  " .. name .. "  " .. ns.FormatMoney(row.c.gold))
  end
  local warband = ns.db.warband.gold
  if warband then
    print("  Warband Bank  " .. ns.FormatMoney(warband))
    total = total + warband
  end
  print("  |cffffd100Total|r  " .. ns.FormatMoney(total))
end

function commands.log(arg)
  local n = tonumber(arg) or 10
  local tx = ns.char.tx
  ns.Print("|cffffd100Last " .. n .. " transactions|r")
  for i = math.max(1, #tx - n + 1), #tx do
    local t = tx[i]
    print(string.format("  %s  %s  %s%s", date("%m-%d %H:%M", t.t), ns.CategoryLabel(t.k),
      ns.FormatMoney(t.a, true), t.r and ("  |cff888888" .. ns.DetailText(t.k, t.r) .. "|r") or ""))
  end
end

-- The saved character matching "Name" or "Name-Realm", or nil.
local function findChar(text)
  local canonical = ns.CanonicalName(text)
  local byName
  for key, c in pairs(ns.db.chars) do
    if ns.CanonicalName(key) == canonical then return key end
    if c.name and c.name:lower() == text:lower() then
      -- Same name on two realms is ambiguous; make the user add the realm.
      byName = byName == nil and key or false
    end
  end
  return byName or nil
end

function commands.forget(arg)
  local target, confirmed = arg:match("^(.-)%s+confirm$")
  target = target or arg
  if target == "" then
    ns.Print("usage: /mp forget Name[-Realm]")
    return
  end
  local key = findChar(target)
  if not key then
    ns.Print("no tracked character matches \"" .. target .. "\" (realm needed if two share a name)")
    return
  end
  local c = ns.db.chars[key]
  if not confirmed then
    ns.Print(string.format("this deletes %s's %d recorded transactions and stops tracking them.", key, #c.tx))
    print("  To proceed: /mp forget " .. key .. " confirm")
    return
  end
  ns.db.chars[key] = nil
  ns.db.ignored[key] = true
  ns.ownChars[ns.CanonicalName(key)] = nil
  if key == ns.charKey then ns.AttachChar() end
  ns.Print("stopped tracking " .. key .. (key == ns.charKey and " (log in on it and /mp track to resume)" or ""))
end

-- Undoes forget for the character you're logged into.
function commands.track()
  if not ns.db.ignored[ns.charKey] then
    ns.Print(ns.charKey .. " is already tracked")
    return
  end
  ns.db.ignored[ns.charKey] = nil
  ns.AttachChar()
  ns.char.gold = GetMoney()
  ns.char.lastSeen = GetServerTime()
  ns.ownChars[ns.CanonicalName(ns.charKey)] = ns.charKey
  ns.Print("tracking " .. ns.charKey .. " again, starting from now")
end

function commands.debug()
  ns.db.settings.debug = not ns.db.settings.debug
  ns.Print("debug " .. (ns.db.settings.debug and "on" or "off"))
end

function commands.help()
  ns.Print("commands:")
  print("  /mp              this session")
  print("  /mp today        today, all characters")
  print("  /mp week         last 7 days, all characters")
  print("  /mp chars        gold per character + warband bank")
  print("  /mp log [n]      last n transactions on this character")
  print("  /mp forget Name  delete a character's ledger and stop tracking it")
  print("  /mp track        resume tracking this character after forget")
  print("  /mp debug        print every transaction as it's recorded")
end

SLASH_MARIPOSA1 = "/mariposa"
SLASH_MARIPOSA2 = "/mp"
SlashCmdList.MARIPOSA = function(msg)
  local cmd, rest = msg:match("^(%S*)%s*(.-)$")
  cmd = cmd:lower()
  if cmd == "" then cmd = "session" end
  ;(commands[cmd] or commands.help)(rest)
end
