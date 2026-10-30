local _, ns = ...

-- Income vs. expense comes from the sign of each transaction. Categories
-- flagged `transfer` move gold between your own pockets and are left out of
-- net totals, like moving money between your own bank accounts.
ns.Categories = {
  quest        = { label = "Quests" },
  world_quest  = { label = "World Quests" },
  bonus        = { label = "Bonus Objectives" },
  loot         = { label = "Loot" },
  pickup       = { label = "Pickup" },
  vendor_sell  = { label = "Vendor Sales" },
  vendor_buy   = { label = "Vendor Purchases" },
  repair       = { label = "Repairs" },
  ah_sale      = { label = "AH Sales" },
  ah_buy       = { label = "AH Purchases" },
  ah_deposit   = { label = "AH Deposits" },
  ah_refund    = { label = "AH Refunds" },
  mail_in      = { label = "Mail Received" },
  mail_out     = { label = "Mail Sent" },
  postage      = { label = "Postage" },
  cod          = { label = "COD Payments" },
  trade_in     = { label = "Trade Received" },
  trade_out    = { label = "Trade Given" },
  flight       = { label = "Flight Paths" },
  transmog     = { label = "Transmog" },
  barber       = { label = "Barber" },
  training     = { label = "Training" },
  crafting_order      = { label = "Crafting Orders" },
  crafting_commission = { label = "Crafting Commissions" },
  container    = { label = "Reward Bags" },
  guild_bank   = { label = "Guild Bank" },
  xfer_warband = { label = "Warband Bank", transfer = true },
  xfer_mail    = { label = "Mail to Alts", transfer = true },
  adjustment   = { label = "Untracked Change" },
  other        = { label = "Other" },
}

function ns.CategoryLabel(cat)
  local info = ns.Categories[cat]
  return info and info.label or cat
end

function ns.IsTransfer(cat)
  local info = ns.Categories[cat]
  return info ~= nil and info.transfer == true
end
