# Stands in for fints_bridge.py in tests (FintsBridge::FAKE_COMMAND): reads the same JSON from stdin, prints
# the same JSON shape. PIN "wrong" fails the way a rejected login does.
require "json"
input = JSON.parse($stdin.read)
abort "Login failed: PIN wrong" if input["pin"] == "wrong"
puts JSON.generate(transactions: [
  { booking_date: "2026-02-03", value_date: "2026-02-04", amount: "-12.34", counterparty: "REWE", iban: "DE89370400440532013000",
    purpose: "Einkauf #{input["iban"]} #{input["start_date"]} EREF: OTHER-REF", raw_type: "Lastschrift", bank_reference: "EREF-9" },
  { booking_date: "2026-02-05", value_date: "2026-02-05", amount: "1500.00", counterparty: "Employer GmbH", iban: nil,
    purpose: "Gehalt EREF: E2E-42 MREF: M-1 CRED: DE98ZZZ09999999999 IBAN: DE02120300000000202051BIC: GENODEF1XXX",
    raw_type: "Gutschrift", bank_reference: nil }
], balance: { amount: "2487.66", date: "2026-02-06" })
