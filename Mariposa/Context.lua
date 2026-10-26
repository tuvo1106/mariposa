local _, ns = ...

-- Tracks which money-related windows are open so an unexplained gold change
-- can be attributed to whatever the player was doing at the time.
local Context = {}
ns.Context = Context

local GRACE = 2 -- seconds a context stays valid after its window closes

local open = {}
local closedAt = {}

function Context:Open(ctx)
  open[ctx] = true
  closedAt[ctx] = nil
end

function Context:Close(ctx)
  -- Some close events fire twice (MERCHANT_CLOSED); only the first counts.
  if open[ctx] then
    open[ctx] = nil
    closedAt[ctx] = GetTime()
  end
end

local function isActive(ctx)
  return open[ctx] or (closedAt[ctx] ~= nil and GetTime() - closedAt[ctx] <= GRACE)
end

-- Most specific first: taking mail at a mailbox beside a vendor counts as mail.
local priority = {
  "loot", "mail", "auction", "trade", "bank", "guildbank",
  "crafting", "merchant", "taxi", "transmog", "barber", "trainer",
}

local categoryFor = {
  loot      = function() return "loot" end,
  mail      = function(d) return d > 0 and "mail_in" or "cod" end,
  auction   = function(d) return d > 0 and "ah_refund" or "ah_buy" end,
  trade     = function(d) return d > 0 and "trade_in" or "trade_out" end,
  bank      = function() return "xfer_warband" end,
  guildbank = function() return "guild_bank" end,
  -- Money earned at the crafting-order kiosk is a commission for fulfilling an
  -- order; money spent is the tip/deposit for placing one.
  crafting  = function(d) return d > 0 and "crafting_commission" or "crafting_order" end,
  merchant  = function(d)
    if d < 0 and InRepairMode() then return "repair" end
    return d > 0 and "vendor_sell" or "vendor_buy"
  end,
  taxi      = function() return "flight" end,
  transmog  = function() return "transmog" end,
  barber    = function() return "barber" end,
  trainer   = function() return "training" end,
}

function Context:Resolve(delta)
  for _, ctx in ipairs(priority) do
    if isActive(ctx) then
      return categoryFor[ctx](delta)
    end
  end
end

-- Modern clients route most NPC windows through
-- PLAYER_INTERACTION_MANAGER_FRAME_SHOW/HIDE. Names are looked up defensively
-- so a renamed or missing enum value doesn't break loading.
local interactions = {}
local function mapInteraction(name, ctx)
  local id = Enum.PlayerInteractionType and Enum.PlayerInteractionType[name]
  if id then interactions[id] = ctx end
end
mapInteraction("Merchant", "merchant")
mapInteraction("Auctioneer", "auction")
mapInteraction("MailInfo", "mail")
mapInteraction("TradePartner", "trade")
mapInteraction("TaxiNode", "taxi")
mapInteraction("Transmogrifier", "transmog")
mapInteraction("Barber", "barber")
mapInteraction("Trainer", "trainer")
mapInteraction("GuildBanker", "guildbank")
mapInteraction("Banker", "bank")
mapInteraction("AccountBanker", "bank")
mapInteraction("CraftingOrders", "crafting")

function Context:OnInteraction(interactionType, isOpen)
  local ctx = interactions[interactionType]
  if not ctx then return end
  if isOpen then self:Open(ctx) else self:Close(ctx) end
end

-- Older per-window events, registered too as a fallback. Core skips any the
-- client doesn't know about.
Context.openEvents = {
  MERCHANT_SHOW = "merchant",
  AUCTION_HOUSE_SHOW = "auction",
  MAIL_SHOW = "mail",
  TRADE_SHOW = "trade",
  TAXIMAP_OPENED = "taxi",
  TRANSMOGRIFY_OPEN = "transmog",
  BARBER_SHOP_OPEN = "barber",
  TRAINER_SHOW = "trainer",
  GUILDBANKFRAME_OPENED = "guildbank",
  BANKFRAME_OPENED = "bank",
  CRAFTINGORDERS_SHOW_CRAFTER = "crafting",
  CRAFTINGORDERS_SHOW_CUSTOMER = "crafting",
  LOOT_OPENED = "loot",
}

Context.closeEvents = {
  MERCHANT_CLOSED = "merchant",
  AUCTION_HOUSE_CLOSED = "auction",
  MAIL_CLOSED = "mail",
  TRADE_CLOSED = "trade",
  TAXIMAP_CLOSED = "taxi",
  TRANSMOGRIFY_CLOSE = "transmog",
  BARBER_SHOP_CLOSE = "barber",
  TRAINER_CLOSED = "trainer",
  GUILDBANKFRAME_CLOSED = "guildbank",
  BANKFRAME_CLOSED = "bank",
  CRAFTINGORDERS_HIDE_CRAFTER = "crafting",
  CRAFTINGORDERS_HIDE_CUSTOMER = "crafting",
  LOOT_CLOSED = "loot",
}
