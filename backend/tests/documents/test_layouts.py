"""Tests for unknown sheet shapes: what the model sees, the checks on its mapping, and reading with a confirmed one."""

import pytest

from app.features.documents.layouts import fingerprint, layout_of, mapping_errors, masked_samples, parse_mapped
from app.features.documents.reader import UnreadableFile, file_kind, read_file


BANK_CSV = (
    b"Account holder,Test Person,PAN ABCDE1234F\n"
    b"\n"
    b"Date,Narration,Withdrawal Amt.,Deposit Amt.\n"
    b"01/10/2026,UPI-SWIGGY,450.00,\n"
    b"02/10/2026,SALARY CREDIT,,95000.00\n"
    b"03/10/2026,bad row,abc,\n"
    )

COLUMNS = {
    "Date": "txn_date",
    "Narration": "description",
    "Withdrawal Amt.": "debit_amount",
    "Deposit Amt.": "credit_amount",
    }


def bank_layout():

    """The layout of the made-up bank statement."""

    sheet = read_file(file_kind("bank.csv", BANK_CSV), BANK_CSV)[0]
    layout = layout_of(sheet)

    assert layout is not None

    return layout


def test_header_found_below_personal_rows() -> None:

    """The header row is found under the account holder lines."""

    layout = bank_layout()

    assert layout.headers == ["Date", "Narration", "Withdrawal Amt.", "Deposit Amt."]
    assert layout.header_index == 2


def test_samples_hide_digits_and_rows_above_header() -> None:

    """The model never sees a digit or anything above the header, such as the PAN line."""

    samples = masked_samples(bank_layout())
    text = " ".join(" ".join(sample) for sample in samples)

    assert not any(character.isdigit() and character != "9" for character in text)
    assert "PAN" not in text and "Test Person" not in text
    assert samples[0][0] == "99/99/9999"


def test_fingerprint_ignores_case_and_spacing() -> None:

    """Two files with the same headers in different case share one fingerprint."""

    assert fingerprint(["Date", "Narration"]) == fingerprint([" date ", "NARRATION"])
    assert fingerprint(["Date", "Narration"]) != fingerprint(["Narration", "Date"])


def test_mapping_checks() -> None:

    """Unknown tables, unknown fields, missing headers, doubled fields and no key field are all refused."""

    headers = list(COLUMNS)

    assert mapping_errors("transactions", COLUMNS, headers) == []
    assert mapping_errors("bank_stuff", COLUMNS, headers)
    assert mapping_errors("transactions", {"Date": "when"}, headers)
    assert mapping_errors("transactions", {"Missing": "amount"}, headers)
    assert mapping_errors("transactions", {"Withdrawal Amt.": "amount", "Deposit Amt.": "amount"}, headers)
    assert mapping_errors("transactions", {"Date": "txn_date"}, headers)
    assert mapping_errors(None, {}, headers) == []


def test_parse_with_confirmed_mapping() -> None:

    """Debit and credit columns become one amount with its direction, and a bad amount is an error, not a guess."""

    layout = bank_layout()
    rows = parse_mapped(layout.sheet, layout.headers, "transactions", COLUMNS)

    assert rows[0].data == {"txn_date": "2026-10-01", "description": "UPI-SWIGGY", "amount": "450.00", "direction": "outflow"}
    assert rows[1].data["direction"] == "inflow"
    assert rows[1].data["amount"] == "95000.00"
    assert rows[2].errors and "debit_amount" in rows[2].errors[0]


def test_renamed_file_refused() -> None:

    """A CSV renamed to .xlsx is refused before it is opened."""

    with pytest.raises(UnreadableFile):
        file_kind("fake.xlsx", BANK_CSV)
