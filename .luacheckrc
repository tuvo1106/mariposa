std = "lua51"
max_line_length = 120
-- Methods defined with `:` don't always use self; that's not a bug.
self = false
exclude_files = { "companion/**" }

globals = { "MariposaDB", "SLASH_MARIPOSA1", "SLASH_MARIPOSA2", "SlashCmdList" }

read_globals = {
  "AutoLootMailItem", "C_AuctionHouse", "C_Bank", "C_ClassColor", "C_Container",
  "C_CraftingOrders", "C_CurrencyInfo",
  "C_EventUtils", "C_Item", "C_Map", "C_QuestLog", "C_TaskQuest", "C_Timer", "CreateFrame", "date",
  "DepositGuildBankMoney", "Enum", "GetCoinTextureString", "GetInboxHeaderInfo",
  "GetInboxInvoiceInfo", "GetMoney", "GetNormalizedRealmName", "GetRealmName",
  "GetSendMailMoney", "GetSendMailPrice", "GetServerTime", "GetTime", "hooksecurefunc",
  "InRepairMode", "MerchantFrame", "RepairAllItems", "SecondsToTime", "SendMail", "strsplit",
  "TakeInboxMoney", "time", "UnitClass", "UnitFactionGroup", "UnitLevel", "UnitName",
  "WithdrawGuildBankMoney",
}
