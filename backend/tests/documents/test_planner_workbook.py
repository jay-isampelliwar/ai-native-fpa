"""Tests for the planner workbook family on a made-up workbook with the same sheet shapes as the real one."""

import io

import openpyxl

from app.features.documents.families import classify
from app.features.documents.parsing import ParseResult
from app.features.documents.reader import file_kind, read_file


def build_workbook() -> bytes:

    """A small planner workbook with made-up values in every kind of sheet."""

    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)

    sheets = {
        "1_Personal_Details": [
            ["1. Personal Details"],
            [],
            ["Plan base date:", "2026-11-01"],
            ["Role", "Name", "Date of Birth", "Age", "City", "Retirement Age", "Life Expectancy"],
            ["Primary Client", "Test User", "1990-01-15", 36, "Pune", 60, 85],
            ["Spouse", "Test Spouse", "1992-05-20", 34, "Pune", 60, 85],
            ],
        "2_Income": [
            ["2. Income — Monthly (INR)"],
            [],
            ["Source", "Member 1", "Member 2", "Is Deduction", "Note to RM"],
            ["Salary", 100000, 50000, "FALSE"],
            ["Other Income", 0, 0, "FALSE"],
            ],
        "3_Expenses": [
            ["3. Expenses — Monthly (INR)"],
            [],
            ["Category", "Section", "Member 1", "Note to RM"],
            ["Groceries & Household", "Essential", 12000],
            ["Home Loan EMI", "Loan EMIs", 30000],
            ],
        "4A_Mutual_Funds": [
            ["Fund Name", "Type", "Folio", "Units", "Current Value", "Strength", "SIP Amount", "Note to RM"],
            ["Test Flexi Cap Fund Direct Growth", "Direct Growth", "12345678", 100.123, 25000, None, 5000],
            ["Test Index Fund", None, "87654321", 50.5, 10000, None, 0],
            ["Empty Fund", None, None, None, 0, None, 0],
            ],
        "4B_Equity_Stocks": [
            ["Stock Name", "ISIN", "Quantity", "Current Price", "Current Value", "Strength", "Horizon", "Note to RM"],
            ["TESTCO", "INE000A01011", 10, 1500, 15000],
            ],
        "8_Loans_Liabilities": [
            ["Loan Type", "Outstanding Amount", "EMI", "Interest Rate", "Tenure", "End Date", "Note to RM"],
            ["Home Loan", 2500000, 30000, 8.5, 180, "2040-01-01"],
            ],
        "9_Insurance_Details": [
            ["Policy Type", "Coverage Type", "Company", "Cover Amount", "Annual Premium", "Maturity Year", "Category", "Members Covered", "Note to RM"],
            ["Status: Not held"],
            ],
        "7_Emergency_Fund": [
            ["7. Emergency Fund"],
            [],
            ["Emergency fund available? (Y/N)", "No"],
            ],
        "Risk_Profile": [
            ["Risk Profile"],
            [],
            ["Question", "Answer", "Score", "Notes"],
            ["Risk Profile", "Moderate"],
            ],
        }

    for name, rows in sheets.items():

        worksheet = workbook.create_sheet(name)

        for row in rows:
            worksheet.append(row)

    buffer = io.BytesIO()
    workbook.save(buffer)

    return buffer.getvalue()


def parse() -> ParseResult:

    """Classify and parse the made-up workbook."""

    data = build_workbook()
    sheets = read_file(file_kind("plan.xlsx", data), data)
    family = classify(sheets)

    assert family is not None and family.name == "planner_workbook"

    return family.parse(sheets)


def rows_for(
    result: ParseResult,
    table: str
    ) -> list:

    """The parsed rows going to one table."""

    return [row for row in result.rows if row.target_table == table]


def test_profile_and_family() -> None:

    """The primary person fills the profile, with the risk answer; the spouse becomes a family member."""

    result = parse()
    profile = rows_for(result, "users")
    family = rows_for(result, "family_members")

    assert len(profile) == 1
    assert profile[0].data["name"] == "Test User"
    assert profile[0].data["retirement_age"] == 60
    assert profile[0].data["risk_appetite"] == "medium"
    assert family[0].data["relation"] == "spouse"


def test_income_per_member_and_zero_rows_skipped() -> None:

    """Each member's income is its own row, and template lines of zero are dropped."""

    income = rows_for(parse(), "income_sources")

    assert [row.data["amount"] for row in income] == ["100000.00", "50000.00"]
    assert income[1].data["name"] == "Salary (Member 2)"
    assert all(row.data["frequency"] == "monthly" for row in income)


def test_loan_emis_not_counted_as_expenses() -> None:

    """EMI lines in the expenses sheet are skipped and named in the sheet note."""

    result = parse()
    expenses = rows_for(result, "expenses")
    note = next(note for note in result.notes if note.sheet == "3_Expenses")

    assert [row.data["name"] for row in expenses] == ["Groceries & Household"]
    assert expenses[0].data["category"] == "groceries"
    assert "Home Loan EMI" in note.message


def test_funds_stocks_and_sip_link() -> None:

    """Funds and stocks become holdings dated by the plan base date, and a SIP row points at its fund."""

    result = parse()
    holdings = rows_for(result, "holdings")
    sips = rows_for(result, "sip_plans")

    assert len(holdings) == 3
    assert holdings[0].data["units"] == "100.1230"
    assert holdings[0].data["folio_number"] == "12345678"
    assert holdings[0].data["as_of_date"] == "2026-11-01"
    assert "sip_amount" not in holdings[0].data
    assert holdings[2].data["isin"] == "INE000A01011"
    assert len(sips) == 1
    assert sips[0].parent is holdings[0]
    assert sips[0].data["amount"] == "5000.00"


def test_evidence_cells_kept() -> None:

    """Every value keeps the sheet, row and cell it came from."""

    holding = rows_for(parse(), "holdings")[0]

    assert holding.source["sheet"] == "4A_Mutual_Funds"
    assert holding.source["row"] == 2
    assert holding.source["cells"]["units"] == "D2"


def test_sheet_notes() -> None:

    """Empty sheets and sheets with no table say so, instead of disappearing."""

    notes = {note.sheet: note for note in parse().notes}

    assert notes["9_Insurance_Details"].outcome == "empty"
    assert "Not held" in notes["9_Insurance_Details"].message
    assert notes["7_Emergency_Fund"].outcome == "not_imported"
    assert notes["4A_Mutual_Funds"].outcome == "imported"


def test_loan_row() -> None:

    """A loan line keeps its amounts, rate, tenure and end date."""

    loan = rows_for(parse(), "loans")[0]

    assert loan.data == {
        "loan_type": "home",
        "outstanding": "2500000.00",
        "emi": "30000.00",
        "interest_rate": "8.50",
        "tenure_months": 180,
        "end_date": "2040-01-01",
        }


def test_unknown_file_has_no_family() -> None:

    """A plain bank CSV matches no family, so it goes to the mapping path."""

    data = b"Date,Narration,Withdrawal Amt.\n01/10/2026,UPI-TEST,250.00\n"

    assert classify(read_file(file_kind("bank.csv", data), data)) is None
