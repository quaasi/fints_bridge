require "open3"
require "json"
require "bigdecimal"
require "date"
require_relative "fints_bridge/version"
require_relative "fints_bridge/bank"

# Talks to German banks over FinTS (PIN/TAN with approval in the banking app) by running
# fints_bridge.py, a thin script around python-fints, through uv. The PIN goes in over stdin, never as an argument.
#
#   bank = FintsBridge.new(url:, blz:, login:, pin:, iban:, product_id:, logger: Rails.logger)
#   bank.transactions(start_date: Date.new(2026, 1, 1)) # => { transactions: [...], balance: { amount:, date: } or nil }
class FintsBridge
  SCRIPT = File.expand_path("fints_bridge/fints_bridge.py", __dir__)
  # Stands in for the script in tests: FintsBridge.command = FintsBridge::FAKE_COMMAND
  FAKE_COMMAND = [ RbConfig.ruby, File.expand_path("fints_bridge/fake.rb", __dir__) ].freeze

  class Error < StandardError; end

  class << self
    attr_accessor :command

    # Downloads Python and python-fints into uv's cache, e.g. while building a Docker image.
    # The script fails on the empty input after its dependencies are in place; that is expected.
    def install!
      Open3.capture2e(*command, stdin_data: "{}")
    end
  end
  self.command = [ "uv", "run", "--quiet", "--script", SCRIPT ].freeze

  def initialize(url:, blz:, login:, pin:, iban:, product_id:, logger: nil)
    # Login and PIN go to this URL; never send them unencrypted.
    raise Error, "The FinTS URL must start with https://" unless url.to_s.match?(%r{\Ahttps://}i)

    @credentials = { url: url, blz: blz, login: login, pin: pin, iban: iban, product_id: product_id }
    @logger = logger
  end

  # Bookings between the dates (end_date defaults to today) and the balance the bank reports now.
  # Rows: booking_date, value_date (Date), amount (BigDecimal), counterparty, iban, purpose, raw_type, bank_reference.
  def transactions(start_date:, end_date: nil)
    result = run(start_date: start_date.iso8601, end_date: end_date&.iso8601)
    transactions = result[:transactions].map do |row|
      row.merge(
        booking_date: Date.iso8601(row[:booking_date]),
        value_date: Date.iso8601(row[:value_date]),
        amount: BigDecimal(row[:amount])
      )
    end
    balance = result[:balance] && { amount: BigDecimal(result[:balance][:amount]), date: Date.iso8601(result[:balance][:date]) }
    { transactions: transactions, balance: balance }
  end

  private
    # Like Open3.capture3, but logs each stderr line (the bank's responses) while the script runs.
    def run(params)
      output, error, status = Open3.popen3(*self.class.command) do |stdin, stdout, stderr, wait|
        stdin.write(@credentials.merge(params).to_json)
        stdin.close
        error_reader = Thread.new do
          stderr.each_line.map { |line| line.tap { @logger&.info("[FinTS] #{line.chomp}") } }.join
        end
        [ stdout.read, error_reader.value, wait.value ]
      end
      raise Error, error.strip.lines.last&.strip || "FinTS request failed" unless status.success?

      JSON.parse(output, symbolize_names: true)
    end
end
