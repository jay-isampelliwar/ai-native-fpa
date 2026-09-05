"""Synthetic workbooks that reproduce the three real layouts without carrying anyone's actual holdings.

The structures here were copied from three real statements; the values were not. A test suite that
depends on someone's personal portfolio cannot be committed, shared or run by anyone else, and the
properties under test - where the header sits, whether a total row is skipped, whether personal
details leak - are properties of the shape rather than of the numbers.

Each builder reproduces the awkward part of its original faithfully, because those are what the
parsers exist to survive. The consolidated layout ends with a total row. The broker layout starts its
table on row twenty three of column B and supplies no value columns. The mutual fund layout puts a
name, a mobile number and a PAN above its table, and writes its percentages as text.

The PAN and mobile number below are invented and follow the format only so that a test asserting they
never reach a staged row is testing something real. They belong to nobody.

Amounts are chosen so that the rows sum exactly to the stated totals. A reconciliation test against a
fixture whose totals were approximated would pass or fail for the wrong reason.
"""

from io import BytesIO

from openpyxl import Workbook

CONSOLIDATED_ROWS = [
    ("AARTIIND", 1140, 467.46, 532906.40, 500.15, 570171.00),
    ("ADOR", 440, 1018.60, 448184.00, 1517.85, 667854.00),
    ("CANBK", 300, 84.31, 25293.00, 129.00, 38700.00),
    ("RELIANCE", 135, 1174.26, 158525.10, 1326.00, 179010.00),
]

BROKER_EQUITY_ROWS = [
    ("360ONE", "INE466L01038", "FINANCIAL SERVICES", 2, 1089.95, 1185.00),
    ("ALLCARGO", "INE418H01029", "LOGISTICS", 50, 67.35, 10.16),
]

BROKER_FUND_ROWS = [
    ("CANARA ROBECO LARGE CAP FUND", "INF760K01FR2", "Equity - Large Cap", 233.888, 64.13, 73.46),
]

FUND_STATEMENT_ROWS = [
    ("UTI Nifty 50 Index Fund Direct", "UTI Mutual Fund", "Equity", "Large Cap", "577346648026", "Groww", 115.376, 12999.36, 19656.86, "10.1%"),
    ("PGIM India Midcap Fund Direct", "PGIM India Mutual Fund", "Equity", "Mid Cap", "91013039353", "Groww", 256.176, 11999.40, 19751.17, "12.39%"),
]


def to_bytes(workbook: Workbook) -> bytes:

    """Render a built workbook to the bytes an upload would carry."""

    buffer = BytesIO()

    workbook.save(buffer)

    return buffer.getvalue()


def consolidated_workbook() -> bytes:

    """Build the consolidated layout: header on row one, no ISIN, and a total row at the end."""

    workbook = Workbook()

    summary = workbook.active
    summary.title = "Portfolio Summary"
    summary["A1"] = "FAMILY PORTFOLIO CONSOLIDATED"
    summary["A2"] = "As of August 11, 2026"
    summary["A4"] = "Metric"
    summary["B4"] = "Value"
    summary["A5"] = "Invested Value"
    summary["B5"] = sum(row[3] for row in CONSOLIDATED_ROWS)
    summary["A6"] = "Current Value"
    summary["B6"] = sum(row[5] for row in CONSOLIDATED_ROWS)

    detail = workbook.create_sheet("Holdings Detail")
    detail.append(
        ["Symbol / Instrument Name", "Quantity", "Buy Avg (₹)", "Buy Value (₹)", "LTP (₹)", "Present Value (₹)"]
    )

    for row in CONSOLIDATED_ROWS:
        detail.append(list(row))

    detail.append(["TOTAL", "", "", sum(row[3] for row in CONSOLIDATED_ROWS), "", sum(row[5] for row in CONSOLIDATED_ROWS)])

    return to_bytes(workbook)


def broker_workbook() -> bytes:

    """Build the broker layout: table on row twenty three of column B, with no value columns at all."""

    workbook = Workbook()

    equity = workbook.active
    equity.title = "Equity"

    equity["B7"] = "Client ID"
    equity["C7"] = "TEST001"
    equity["B11"] = "Equity Holdings Statement as on 2026-08-25"
    equity["B13"] = "Summary"
    equity["B15"] = "Invested Value"
    equity["C15"] = sum(row[3] * row[4] for row in BROKER_EQUITY_ROWS)
    equity["B16"] = "Present Value"
    equity["C16"] = sum(row[3] * row[5] for row in BROKER_EQUITY_ROWS)

    headers = ["Symbol", "ISIN", "Sector", "Quantity Available", "Average Price", "Previous Closing Price"]

    for column, header in enumerate(headers, start=2):
        equity.cell(row=23, column=column, value=header)

    for offset, row in enumerate(BROKER_EQUITY_ROWS, start=24):
        for column, value in enumerate(row, start=2):
            equity.cell(row=offset, column=column, value=value)

    funds = workbook.create_sheet("Mutual Funds")
    funds["B7"] = "Client ID"
    funds["C7"] = "TEST001"
    funds["B15"] = "Invested Value"
    funds["C15"] = sum(row[3] * row[4] for row in BROKER_FUND_ROWS)
    funds["B16"] = "Present Value"
    funds["C16"] = sum(row[3] * row[5] for row in BROKER_FUND_ROWS)

    fund_headers = ["Symbol", "ISIN", "Instrument Type", "Quantity Available", "Average Price", "Previous Closing Price"]

    for column, header in enumerate(fund_headers, start=2):
        funds.cell(row=23, column=column, value=header)

    for offset, row in enumerate(BROKER_FUND_ROWS, start=24):
        for column, value in enumerate(row, start=2):
            funds.cell(row=offset, column=column, value=value)

    return to_bytes(workbook)


def fund_statement_workbook() -> bytes:

    """Build the mutual fund layout: personal details above the table and percentages stored as text."""

    workbook = Workbook()

    sheet = workbook.active
    sheet.title = "Holdings"

    sheet["A3"] = "Personal Details"
    sheet["A4"] = "Name"
    sheet["B4"] = "Test Person"
    sheet["A5"] = "Mobile Number"
    sheet["B5"] = "9000000000"
    sheet["A6"] = "PAN"
    sheet["B6"] = "AAAPZ1234C"

    sheet["A10"] = "HOLDING SUMMARY"
    sheet["A13"] = "Total Investments"
    sheet["B13"] = "Current Portfolio Value"
    sheet["A14"] = sum(row[7] for row in FUND_STATEMENT_ROWS)
    sheet["B14"] = sum(row[8] for row in FUND_STATEMENT_ROWS)

    sheet["A18"] = "HOLDINGS AS ON 2026-07-21"

    headers = ["Scheme Name", "AMC", "Category", "Sub-category", "Folio No.", "Source", "Units", "Invested Value", "Current Value", "XIRR"]

    for column, header in enumerate(headers, start=1):
        sheet.cell(row=21, column=column, value=header)

    for offset, row in enumerate(FUND_STATEMENT_ROWS, start=23):
        for column, value in enumerate(row, start=1):
            sheet.cell(row=offset, column=column, value=value)

    return to_bytes(workbook)


def unknown_workbook() -> bytes:

    """Build a tabular workbook no template covers, which must ask for a mapping rather than guess."""

    workbook = Workbook()

    sheet = workbook.active
    sheet.title = "Positions"

    sheet.append(["Security Code", "Description", "Qty Available", "Cost Per Unit", "Current Amount"])
    sheet.append(["INE001A01036", "HDFC Bank Limited", 25, 1520.50, 41000.00])
    sheet.append(["INE009A01021", "Infosys Limited", 40, 1410.25, 58000.00])

    return to_bytes(workbook)
