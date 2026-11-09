# fints_bridge

FinTS online banking for Ruby apps: fetch an account's bookings and balance from a German bank,
with the login approved in the bank's app (decoupled PIN/TAN). The banking itself is done by
[python-fints](https://github.com/raphaelm/python-fints), run as a subprocess through
[uv](https://docs.astral.sh/uv/). Also ships a directory of all German bank codes with their FinTS server URLs.

## Usage

```ruby
bank = FintsBridge.new(
  url: "https://fints.dkb.de/fints", blz: "12030000", login: "online-banking-name", pin: pin,
  iban: "DE02...", product_id: Rails.application.credentials.fints_product_id, logger: Rails.logger
)
result = bank.transactions(start_date: Date.new(2026, 1, 1)) # end_date: defaults to today
result[:transactions] # => [{ booking_date:, value_date:, amount: BigDecimal, counterparty:, iban:, purpose:, raw_type:, bank_reference: }]
result[:balance]      # => { amount: BigDecimal, date: } or nil if the bank does not report it
```

The call blocks until the login is approved in the banking app (up to 5 minutes), so run it in a background job.
Failures raise `FintsBridge::Error` with a one-line message that includes the bank's own error texts.
Only app approval is supported; a bank that wants a typed TAN fails with a clear message.

### Bank directory

```ruby
bank = FintsBridge::Bank.find("DE02 1203 0000 0000 2020 51") # also a BLZ ("12030000") or BIC ("BYLADEM1001")
bank.name      # => "Deutsche Kreditbank Berlin"
bank.fints_url # => "https://fints.dkb.de/fints" (nil if the bank has no FinTS PIN/TAN server)
```

The data comes from [hbci4java](https://github.com/hbci4j/hbci4java)'s `blz.properties` (LGPL-2.1,
see `data/LICENSE-blz.txt`). Refresh it with `rake banks:update`.

### Tests in your app

```ruby
FintsBridge.command = FintsBridge::FAKE_COMMAND # fixed bookings; PIN "wrong" fails like a rejected login
```

## Setup

### uv

The app host needs `uv` on the PATH; uv fetches Python and python-fints on first use. In a Dockerfile:

```dockerfile
COPY --from=ghcr.io/astral-sh/uv:0.5.9 /uv /usr/local/bin/uv
# ... after the app and its gems are in place, as the user that runs the app:
RUN bundle exec ruby -rfints_bridge -e FintsBridge.install!
```

### Product registration

Banks only answer registered FinTS products. Register each app once with the Deutsche Kreditwirtschaft:

1. Fill in the PDF form "FinTS-Produktregistrierung" (on <https://www.hbci-zka.de>):
   product name exactly as the app is called, category "Web-Server", registration number empty,
   "FinTS-Verteiler: j" to receive the official bank list.
2. Email it to registrierung@hbci-zka.de. The number arrives after about 10-15 working days.
3. Pass it as `product_id:`. Several deployments of the same app share one number.

### Known bank quirks handled

- Banks without MT940 (e.g. MLP/Atruvia) are asked for camt.052 in the newest version they list.
- Error texts the bank only sends while bootstrapping (e.g. "9078 FinTS-Produkt ist nicht registriert") are surfaced.

## Development

```sh
bundle install
bundle exec rake # Ruby tests and the Python checks
```
