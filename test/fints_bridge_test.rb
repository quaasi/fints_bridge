require "minitest/autorun"
require_relative "../lib/fints_bridge"

class FintsBridgeTest < Minitest::Test
  def setup
    @original = FintsBridge.command
    FintsBridge.command = FintsBridge::FAKE_COMMAND
  end

  def teardown
    FintsBridge.command = @original
  end

  def bank(pin: "12345")
    FintsBridge.new(url: "https://fints.example", blz: "12030000", login: "me", pin: pin, iban: "DE02120300000000202051", product_id: "X")
  end

  def test_transactions_come_back_typed
    result = bank.transactions(start_date: Date.new(2026, 2, 1))

    first = result[:transactions].first
    assert_equal Date.new(2026, 2, 3), first[:booking_date]
    assert_equal Date.new(2026, 2, 4), first[:value_date]
    assert_equal BigDecimal("-12.34"), first[:amount]
    assert_includes first[:purpose], "DE02120300000000202051 2026-02-01" # the fake echoes IBAN and start date
    assert_equal({ amount: BigDecimal("2487.66"), date: Date.new(2026, 2, 6) }, result[:balance])
  end

  def test_failure_raises_the_last_error_line
    error = assert_raises(FintsBridge::Error) { bank(pin: "wrong").transactions(start_date: Date.new(2026, 2, 1)) }
    assert_equal "Login failed: PIN wrong", error.message
  end

  def test_refuses_a_url_without_https
    error = assert_raises(FintsBridge::Error) do
      FintsBridge.new(url: "http://fints.example", blz: "1", login: "me", pin: "1", iban: "DE1", product_id: "X")
    end
    assert_equal "The FinTS URL must start with https://", error.message
  end

  def test_find_bank_by_blz_iban_or_bic
    dkb = FintsBridge::Bank.find("12030000")
    assert_equal "BYLADEM1001", dkb.bic
    assert_equal "https://fints.dkb.de/fints", dkb.fints_url

    assert_equal dkb, FintsBridge::Bank.find("de02 1203 0000 0000 2020 51")
    assert_equal dkb, FintsBridge::Bank.find("BYLADEM1001")
    assert_equal "https://fints2.atruvia.de/cgi-bin/hbciservlet", FintsBridge::Bank.find("MLPBDE61").fints_url
    assert_nil FintsBridge::Bank.find("99999999")
    assert_nil FintsBridge::Bank.find("not a code")
  end
end
