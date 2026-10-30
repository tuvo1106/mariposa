local _, ns = ...

function ns.Print(...)
  print("|cffff9a1fMariposa|r:", ...)
end

local coinString = C_CurrencyInfo and C_CurrencyInfo.GetCoinTextureString or GetCoinTextureString

function ns.FormatMoney(copper, signed)
  copper = copper or 0
  local text = coinString(math.abs(copper))
  if copper < 0 then
    return "|cffff5555-|r" .. text
  elseif signed and copper > 0 then
    return "|cff55ff55+|r" .. text
  end
  return text
end

-- Categories whose detail is a quest ID.
ns.QUEST_CATEGORIES = { quest = true, world_quest = true, bonus = true }

-- A transaction's detail as shown in game: a quest reward stores the quest's ID
-- and shows its title once the addon has looked it up (see Core.lua).
function ns.DetailText(cat, ref)
  if ref == nil then return nil end
  local names = ns.QUEST_CATEGORIES[cat] and ns.db and ns.db.questNames
  return names and names[tonumber(ref)] or tostring(ref)
end

-- "Name-Realm" lowercased with spaces/hyphens/apostrophes stripped from the
-- realm, so "Alt-Area 52", "alt-Area52" and "Alt" (same realm) all compare equal.
function ns.CanonicalName(name)
  if not name or name == "" then return nil end
  local base, realm = strsplit("-", name, 2)
  realm = realm or GetNormalizedRealmName() or ""
  return (base .. "-" .. realm:gsub("[%s%-']", "")):lower()
end

function ns.IsOwnCharacter(name)
  local key = ns.CanonicalName(name)
  return key ~= nil and key ~= ns.CanonicalName(ns.charKey) and ns.ownChars[key] ~= nil
end
