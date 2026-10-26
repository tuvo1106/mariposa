local _, ns = ...

-- Post-hooks on Blizzard API calls that tell us *why* money is about to move.
-- hooksecurefunc runs after the original call but before the server responds,
-- so mail and send-mail state is still readable here.

local function expect(...)
  ns.Ledger:Expect(...)
end

-- Repairs ---------------------------------------------------------------------

hooksecurefunc("RepairAllItems", function(useGuildBank)
  if not useGuildBank then expect("repair", nil, nil, -1) end
end)

-- Auction house ---------------------------------------------------------------

if C_AuctionHouse then
  for _, fn in ipairs({ "PostItem", "PostCommodity" }) do
    if C_AuctionHouse[fn] then
      hooksecurefunc(C_AuctionHouse, fn, function() expect("ah_deposit", nil, nil, -1) end)
    end
  end
end

-- Mail ------------------------------------------------------------------------

local function expectMailMoney(index)
  local _, _, sender, _, money = GetInboxHeaderInfo(index)
  if not money or money <= 0 then return end
  local invoiceType, itemName = GetInboxInvoiceInfo(index)
  if invoiceType == "seller" then
    expect("ah_sale", money, itemName)
  elseif ns.IsOwnCharacter(sender) then
    expect("xfer_mail", money, sender)
  else
    expect("mail_in", money, sender)
  end
end

hooksecurefunc("TakeInboxMoney", expectMailMoney)
hooksecurefunc("AutoLootMailItem", expectMailMoney)

hooksecurefunc("SendMail", function(recipient)
  local money = GetSendMailMoney() or 0
  if money > 0 then
    expect(ns.IsOwnCharacter(recipient) and "xfer_mail" or "mail_out", -money, recipient)
  end
  local postage = GetSendMailPrice() or 0
  if postage > 0 then expect("postage", -postage) end
end)

-- Warband & guild bank --------------------------------------------------------

if C_Bank then
  local function bankCategory(bankType)
    return bankType == Enum.BankType.Guild and "guild_bank" or "xfer_warband"
  end
  if C_Bank.DepositMoney then
    hooksecurefunc(C_Bank, "DepositMoney", function(bankType, amount)
      if amount then expect(bankCategory(bankType), -amount) end
    end)
  end
  if C_Bank.WithdrawMoney then
    hooksecurefunc(C_Bank, "WithdrawMoney", function(bankType, amount)
      if amount then expect(bankCategory(bankType), amount) end
    end)
  end
end

if DepositGuildBankMoney then
  hooksecurefunc("DepositGuildBankMoney", function(amount) expect("guild_bank", -amount) end)
end
if WithdrawGuildBankMoney then
  hooksecurefunc("WithdrawGuildBankMoney", function(amount) expect("guild_bank", amount) end)
end

-- Crafting orders -------------------------------------------------------------
-- Placing an order deducts the tip (and any listing deposit) immediately. The
-- tip is the amount we can read up front; a separate deposit, and the crafter's
-- commission on the other side, are left to the crafting-order window context.

if C_CraftingOrders and C_CraftingOrders.PlaceOrder then
  hooksecurefunc(C_CraftingOrders, "PlaceOrder", function(orderInfo)
    local tip = type(orderInfo) == "table" and orderInfo.tipAmount
    if tip and tip > 0 then expect("crafting_order", -tip) end
  end)
end
