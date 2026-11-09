# /// script
# requires-python = ">=3.11"
# dependencies = ["fints>=4,<5"]
# ///
"""Fetch one account's transactions via FinTS (PIN/TAN with approval in the banking app).

Called by FintsBridge#transactions (lib/fints_bridge.rb). Reads JSON from stdin:
  {url, blz, login, pin, iban, start_date, end_date (optional), product_id}
Prints {"transactions": [rows, see to_row], "balance": {"amount", "date"} or null} to stdout.
On failure, prints a one-line message to stderr and exits non-zero.
"""
import json
import logging
import re
import sys
import time
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree

from fints.client import FinTS3PinTanClient, NeedTANResponse
from fints.connection import FinTSHTTPSConnection
from fints.exceptions import FinTSUnsupportedOperation
from fints.formals import SupportedMessageTypes
from fints.segments.statement import HKCAZ1

APPROVAL_TIMEOUT_SECONDS = 300

# The bank's warnings and errors (e.g. "product not registered") only reach the library's log;
# collect them so they end up in the one-line error message.
bank_messages = []


class CollectBankMessages(logging.Handler):
    def emit(self, record):
        message = record.getMessage().removeprefix("Dialog response: ")
        if message not in bank_messages:
            bank_messages.append(message)


fints_logger = logging.getLogger("fints")
fints_logger.setLevel(logging.INFO)  # not DEBUG: that level dumps raw messages including the PIN
fints_logger.addHandler(CollectBankMessages(logging.WARNING))
progress = logging.StreamHandler(sys.stderr)  # FintsBridge passes these lines to its logger
progress.setFormatter(logging.Formatter("%(message)s"))
fints_logger.addHandler(progress)
fints_logger.propagate = False


# The library does not log responses while bootstrapping (fetching TAN methods), so an error like
# "9078 FinTS-Produkt ist nicht registriert" would hide behind the HTTP 400 DKB sends for the dialog end.
send_message = FinTSHTTPSConnection.send


def send_and_collect_errors(self, msg):
    response = send_message(self, msg)
    for segment in response.find_segments(("HIRMG", "HIRMS")):
        for answer in segment.responses:
            text = f"{answer.code} - {answer.text}"
            if answer.code.startswith("9") and text not in bank_messages:
                bank_messages.append(text)
    return response


FinTSHTTPSConnection.send = send_and_collect_errors


def fail(message):
    if bank_messages:
        message += " | Bank: " + "; ".join(bank_messages)
    print(message, file=sys.stderr)
    sys.exit(1)


def choose_app_approval(client):
    client.fetch_tan_mechanisms()
    mechanisms = client.get_tan_mechanisms()
    decoupled = [key for key, m in mechanisms.items() if getattr(m, "decoupled_max_poll_number", None) is not None]
    # ponytail: picks the first app-approval method; add a per-account choice if a bank offers several
    if decoupled:
        client.set_tan_mechanism(decoupled[0])
    elif len(mechanisms) == 1:
        client.set_tan_mechanism(next(iter(mechanisms)))
    else:
        fail("The bank offers no app-approval method. Available: " + ", ".join(m.name for m in mechanisms.values()))

    if client.is_tan_media_required() and not client.selected_tan_medium:
        _, media = client.get_tan_media()
        client.set_tan_medium(media[0])


def wait_for_approval(client, response):
    deadline = time.monotonic() + APPROVAL_TIMEOUT_SECONDS
    while isinstance(response, NeedTANResponse):
        if not response.decoupled:
            fail("The bank asks for a TAN to be typed in, which is not supported yet. Use app approval instead.")
        if time.monotonic() > deadline:
            fail("No approval in the banking app within 5 minutes. Please try again.")
        time.sleep(3)
        response = client.send_tan(response, "")
    return response


def to_row(transaction):
    data = transaction.data
    booking_date = data.get("entry_date") or data["date"]
    return {
        "booking_date": booking_date.isoformat(),
        "value_date": (data.get("date") or booking_date).isoformat(),
        "amount": str(data["amount"].amount),
        "counterparty": data.get("applicant_name") or data.get("posting_text") or "Unknown",
        "iban": data.get("applicant_iban"),
        "purpose": data.get("purpose"),
        "raw_type": data.get("posting_text"),
        "bank_reference": data.get("end_to_end_reference") or None,
    }


def camt_rows(document):
    """Booked entries of one camt.052 XML document, in the same row shape as to_row."""
    rows = []
    for entry in ElementTree.fromstring(document).iterfind(".//{*}Ntry"):
        def text(path, node=entry):
            found = node.find(path)
            return found.text.strip() if found is not None and found.text else None

        amount = Decimal(text("{*}Amt"))
        credit = text("{*}CdtDbtInd") == "CRDT"
        booking_date = text("{*}BookgDt/{*}Dt") or text("{*}BookgDt/{*}DtTm")[:10]
        # ponytail: one row per entry from the first transaction detail; split batch bookings if a bank sends them
        details = entry.find("{*}NtryDtls/{*}TxDtls")
        if details is None:
            details = entry
        party = "Dbtr" if credit else "Cdtr"
        # MLP cuts the purpose into fixed-width lines mid-word ("I" / "BAN: "), and its CSV export joins
        # them without a space; doing the same keeps the purposes equal for the duplicate check.
        # ponytail: glues words for banks that send one word-aligned line per Ustrd; join per bank if one does
        purpose = "".join(line.text for line in details.iterfind("{*}RmtInf/{*}Ustrd") if line.text).strip()
        reference = text("{*}Refs/{*}EndToEndId", details)
        rows.append({
            "booking_date": booking_date,
            "value_date": text("{*}ValDt/{*}Dt") or booking_date,
            "amount": str(amount if credit else -amount),
            "counterparty": text(f"{{*}}RltdPties/{{*}}{party}//{{*}}Nm", details) or text("{*}AddtlNtryInf") or "Unknown",
            "iban": text(f"{{*}}RltdPties/{{*}}{party}Acct/{{*}}Id/{{*}}IBAN", details),
            "purpose": purpose or None,
            "raw_type": text("{*}AddtlNtryInf"),
            "bank_reference": None if reference in (None, "NOTPROVIDED") else reference,
        })
    return rows


def bank_camt_format(client):
    """Newest camt.052 version the bank lists in HICAZS; the library always asks for .001.02, which e.g. MLP rejects."""
    versions = [int(v) for v in re.findall(rb"camt\.052\.001\.(\d+)", client.bpd.render_bytes())]
    return f"urn:iso:std:iso:20022:tech:xsd:camt.052.001.{max(versions, default=2):02d}"


def get_transactions_camt(client, account, start_date, end_date):
    # Same as FinTS3Client.get_transactions_xml, but with the camt version the bank accepts.
    camt_format = bank_camt_format(client)
    fints_logger.info("No MT940 at this bank, requesting %s", camt_format)
    with client._get_dialog() as dialog:
        hkcaz = client._find_highest_supported_command(HKCAZ1)
        return client._fetch_with_touchdowns(
            dialog,
            lambda touchdown: hkcaz(
                account=hkcaz._fields["account"].type.from_sepa_account(account),
                all_accounts=False,
                date_start=start_date,
                date_end=end_date,
                touchdown_point=touchdown,
                supported_camt_messages=SupportedMessageTypes([camt_format]),
            ),
            FinTS3PinTanClient._response_handler_get_transactions_xml,
            "HICAZ",
        )


def fetch_rows(client, account, start_date, end_date):
    try:
        transactions = wait_for_approval(client, client.get_transactions(account, start_date, end_date))
        return [to_row(t) for t in transactions]
    except FinTSUnsupportedOperation:
        # Some banks (e.g. MLP/Atruvia) offer only camt XML (HKCAZ), not MT940 (HKKAZ).
        try:
            booked, _pending = wait_for_approval(client, get_transactions_camt(client, account, start_date, end_date))
        except FinTSUnsupportedOperation as e:
            offered = sorted({s.header.type for s in client.bpd.segments})
            fail(f"FinTSUnsupportedOperation: {e} Bank offers: {', '.join(offered) or 'nothing'}")
        return [row for document in booked for row in camt_rows(document)]


def fetch_balance(client, account):
    """The booked balance the bank reports now (HKSAL), or None if the bank does not offer it."""
    try:
        balance = wait_for_approval(client, client.get_balance(account))
    except FinTSUnsupportedOperation:
        return None
    return {"amount": str(balance.amount.amount), "date": balance.date.isoformat()}


def main():
    params = json.load(sys.stdin)
    if not params.get("product_id"):
        fail("FinTS product registration ID is not configured.")

    client = FinTS3PinTanClient(
        params["blz"], params["login"], params["pin"], params["url"], product_id=params["product_id"]
    )
    choose_app_approval(client)

    with client:
        if client.init_tan_response:
            client.init_tan_response = wait_for_approval(client, client.init_tan_response)

        accounts = wait_for_approval(client, client.get_sepa_accounts())
        iban = params["iban"].replace(" ", "").upper()
        account = next((a for a in accounts if a.iban == iban), None)
        if account is None:
            fail(f"Account {iban} was not found at this bank login.")

        rows = fetch_rows(
            client,
            account,
            date.fromisoformat(params["start_date"]),
            date.fromisoformat(params["end_date"]) if params.get("end_date") else date.today(),
        )
        balance = fetch_balance(client, account)

    json.dump({"transactions": rows, "balance": balance}, sys.stdout)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 - one readable line for the caller, no traceback with PIN-bearing locals
        fail(f"{type(e).__name__}: {e}")
