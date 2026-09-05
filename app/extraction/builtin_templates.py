"""The template families already known, one entry per provider layout rather than per file.

Three real statements were read to build these, and each taught something the others did not. The
consolidated export has no ISIN and ends with a formula total row. The broker export starts its table
on row twenty three of column B and supplies no invested or current value, only quantity and two
prices. The mutual fund statement puts a name, a mobile number and a PAN above its table.

Fingerprints are left unset here. A built in template is matched by its sheet and column shape rather
than by a stored hash, so a provider adding a column at the end still matches; a learned template,
by contrast, is matched by fingerprint because it was confirmed against one exact layout.

Aliases are generous on purpose. "Quantity Available", "Qty Available", "Units" and "Quantity" all
mean the same thing across these three files alone, and a template that survives a provider renaming
one heading is worth more than one that is precise about a single export.

Asset type is set per sheet where the sheet itself says it. A broker's "Equity" and "Mutual Funds"
tabs are the strongest signal available about what their rows are, stronger than anything in the rows.

Adding a provider is adding an entry here. That is the intended cost of a new format, and it is why
nothing in the parsing code knows any provider's name.
"""

from app.extraction.templates import SheetSpec, TemplateSpec

CONSOLIDATED_HOLDINGS = TemplateSpec(
    id="consolidated_holdings.v1",
    name="Consolidated family holdings export",
    provider="consolidated",
    sheets=[
        SheetSpec(
            name_contains="Holdings Detail",
            header_row=1,
            asset_type="equity",
            mapping={
                "instrument_name": ["Symbol / Instrument Name", "Instrument", "Symbol"],
                "symbol": ["Symbol / Instrument Name", "Symbol"],
                "quantity": ["Quantity", "Qty"],
                "average_cost": ["Buy Avg", "Buy Avg (₹)", "Average Price"],
                "invested_value": ["Buy Value", "Buy Value (₹)", "Invested Value"],
                "last_price": ["LTP", "LTP (₹)", "Last Price"],
                "current_value": ["Present Value", "Present Value (₹)", "Current Value"],
            },
        )
    ],
)

BROKER_HOLDINGS = TemplateSpec(
    id="broker_holdings.v1",
    name="Broker equity and mutual fund holdings statement",
    provider="broker",
    sheets=[
        SheetSpec(
            name_contains="Equity",
            header_row=23,
            asset_type="equity",
            account_label="broker",
            mapping={
                "instrument_name": ["Symbol"],
                "symbol": ["Symbol"],
                "isin": ["ISIN"],
                "quantity": ["Quantity Available", "Qty Available", "Quantity"],
                "average_cost": ["Average Price", "Avg Price"],
                "last_price": ["Previous Closing Price", "Closing Price", "LTP"],
            },
        ),
        SheetSpec(
            name_contains="Mutual Funds",
            header_row=23,
            asset_type="mutual_fund",
            account_label="broker",
            mapping={
                "instrument_name": ["Symbol"],
                "symbol": ["Symbol"],
                "isin": ["ISIN"],
                "asset_type": ["Instrument Type"],
                "quantity": ["Quantity Available", "Units"],
                "average_cost": ["Average Price"],
                "last_price": ["Previous Closing Price", "NAV"],
            },
        ),
    ],
)

MUTUAL_FUND_STATEMENT = TemplateSpec(
    id="mutual_fund_statement.v1",
    name="Mutual fund holdings statement",
    provider="mutual_fund_platform",
    sheets=[
        SheetSpec(
            name_contains="Holdings",
            header_row=21,
            asset_type="mutual_fund",
            mapping={
                "instrument_name": ["Scheme Name", "Scheme"],
                "symbol": ["Scheme Name"],
                "folio_id": ["Folio No.", "Folio Number", "Folio"],
                "source": ["Source", "Platform"],
                "asset_type": ["Category"],
                "quantity": ["Units", "Quantity"],
                "invested_value": ["Invested Value", "Total Investments"],
                "current_value": ["Current Value", "Current Portfolio Value"],
            },
        )
    ],
)

BUILTIN_TEMPLATES = [
    BROKER_HOLDINGS,
    MUTUAL_FUND_STATEMENT,
    CONSOLIDATED_HOLDINGS,
]
