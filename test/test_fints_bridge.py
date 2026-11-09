# Run: rake test:python
import importlib.util
import pathlib

path = pathlib.Path(__file__).resolve().parents[1] / "lib/fints_bridge/fints_bridge.py"
spec = importlib.util.spec_from_file_location("fints_bridge", path)
fints_bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fints_bridge)

CAMT = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.052.001.02"><BkToCstmrAcctRpt><Rpt>
  <Ntry>
    <Amt Ccy="EUR">42.50</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts>BOOK</Sts>
    <BookgDt><Dt>2026-11-03</Dt></BookgDt><ValDt><Dt>2026-11-02</Dt></ValDt>
    <NtryDtls><TxDtls>
      <Refs><EndToEndId>E2E-1</EndToEndId></Refs>
      <RltdPties><Cdtr><Nm>Stadtwerke</Nm></Cdtr><CdtrAcct><Id><IBAN>DE02120300000000202051</IBAN></Id></CdtrAcct></RltdPties>
      <RmtInf><Ustrd>Abschlag Nov</Ustrd><Ustrd>ember EREF: E2E-1 I</Ustrd><Ustrd>BAN: DE02</Ustrd></RmtInf>
    </TxDtls></NtryDtls>
    <AddtlNtryInf>Lastschrift</AddtlNtryInf>
  </Ntry>
  <Ntry>
    <Amt Ccy="EUR">1000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts>BOOK</Sts>
    <BookgDt><DtTm>2026-11-04T10:00:00</DtTm></BookgDt>
    <NtryDtls><TxDtls>
      <Refs><EndToEndId>NOTPROVIDED</EndToEndId></Refs>
      <RltdPties><Dbtr><Nm>Arbeitgeber GmbH</Nm></Dbtr></RltdPties>
    </TxDtls></NtryDtls>
  </Ntry>
</Rpt></BkToCstmrAcctRpt></Document>"""

debit, credit = fints_bridge.camt_rows(CAMT)
assert debit == {
    "booking_date": "2026-11-03", "value_date": "2026-11-02", "amount": "-42.50", "counterparty": "Stadtwerke",
    "iban": "DE02120300000000202051", "purpose": "Abschlag November EREF: E2E-1 IBAN: DE02", "raw_type": "Lastschrift",
    "bank_reference": "E2E-1",
}, debit
assert credit["amount"] == "1000.00" and credit["counterparty"] == "Arbeitgeber GmbH", credit
assert credit["booking_date"] == credit["value_date"] == "2026-11-04", credit
assert credit["bank_reference"] is None and credit["purpose"] is None, credit
class FakeBpd:
    def __init__(self, data):
        self.data = data

    def render_bytes(self):
        return self.data


class FakeClient:
    def __init__(self, data):
        self.bpd = FakeBpd(data)


bpd = b"HICAZS:1:1+1+1+0+450:N:N:urn?:iso?:std?:iso?:20022?:tech?:xsd?:camt.052.001.02:urn?:iso?:std?:iso?:20022?:tech?:xsd?:camt.052.001.08'"
assert fints_bridge.bank_camt_format(FakeClient(bpd)) == "urn:iso:std:iso:20022:tech:xsd:camt.052.001.08"
assert fints_bridge.bank_camt_format(FakeClient(b"")) == "urn:iso:std:iso:20022:tech:xsd:camt.052.001.02"

print("ok")
