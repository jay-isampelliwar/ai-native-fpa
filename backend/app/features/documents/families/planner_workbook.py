"""The planner workbook family: one sheet per section, from personal details to goals, each read by its own rules."""

from collections.abc import Callable
from dataclasses import dataclass, field

from app.features.documents.fields import pick_choice
from app.features.documents.normalize import NotReadable, header_key, to_date
from app.features.documents.parsing import (
    ParsedRow,
    ParseResult,
    RowBuilder,
    SheetNote,
    data_rows,
    find_header,
    first_text,
    )
from app.features.documents.reader import Cell, Sheet


FAMILY = "planner_workbook"

MIN_MATCHED_SHEETS = 4

BASE_DATE_LABEL = "plan base date"


@dataclass
class Context:

    """What one sheet's rules need from the others: the plan date and the user's own profile row."""

    base_date: str | None = None
    profile: RowBuilder | None = None
    rows: list[ParsedRow] = field(default_factory=list)


Handler = Callable[[Sheet, int, Context], SheetNote | None]


@dataclass
class SheetRule:

    """One known sheet: the headers that identify it and the rule that reads it."""

    name: str
    headers: frozenset[str]
    handler: Handler


def keep(
    builder: RowBuilder,
    context: Context
    ) -> bool:

    """Add the built row when it holds a real record, and say whether it did."""

    if not builder.has_content():
        return False

    context.rows.append(builder.row)

    return True


def cell_text(cell: Cell | None) -> str:

    """The tidied text of a cell, empty when the cell is blank."""

    return header_key(cell.value) if cell is not None else ""


def member_columns(cells: dict[str, Cell | None]) -> list[str]:

    """The per-member amount columns, such as 'member 1' and 'member 2', in sheet order."""

    return [key for key in cells if key.startswith("member")]


def monthly_title(sheet: Sheet) -> bool:

    """Whether the sheet's title says its amounts are monthly."""

    return any("monthly" in header_key(value) for value in sheet.row_values(0) if value is not None) if sheet.rows else False


def read_personal(
    sheet: Sheet,
    header: int,
    context: Context
    ) -> None:

    """The primary person updates the user's profile; everyone else becomes a family member."""

    for row_number, cells in data_rows(sheet, header):

        role = cell_text(cells.get("role"))

        if not role:
            continue

        if any(word in role for word in ("primary", "self", "client")):

            builder = context.profile or RowBuilder("users", sheet, row_number)
            builder.put("name", cells.get("name"))
            builder.put("date_of_birth", cells.get("date of birth"))
            builder.put("city", cells.get("city"))
            builder.put("retirement_age", cells.get("retirement age"))
            builder.put("life_expectancy", cells.get("life expectancy"))

            if context.profile is None:
                context.profile = builder
                context.rows.append(builder.row)

            continue

        builder = RowBuilder("family_members", sheet, row_number)
        builder.put("name", cells.get("name"))
        builder.put("relation", cells.get("role"))
        builder.put("date_of_birth", cells.get("date of birth"))
        keep(builder, context)


def read_risk(
    sheet: Sheet,
    header: int,
    context: Context
    ) -> SheetNote | None:

    """Only the final 'Risk Profile' answer is read, into the user's profile."""

    for row_number, cells in data_rows(sheet, header):

        if cell_text(cells.get("question")) != "risk profile" or cells.get("answer") is None:
            continue

        if context.profile is None:
            context.profile = RowBuilder("users", sheet, row_number)
            context.rows.append(context.profile.row)

        context.profile.put("risk_appetite", cells.get("answer"))

        return SheetNote(sheet.name, "imported", "Risk profile added to your profile", 1)

    return SheetNote(sheet.name, "empty", "Sheet found, but no final risk profile answer")


def read_income(
    sheet: Sheet,
    header: int,
    context: Context
    ) -> SheetNote | None:

    """One income row per source and member with an amount above zero; deduction lines are skipped."""

    frequency = "monthly" if monthly_title(sheet) else None
    skipped = []

    for row_number, cells in data_rows(sheet, header):

        source = cells.get("source")

        if source is None:
            continue

        if cell_text(cells.get("is deduction")) in ("true", "yes"):
            skipped.append(str(source.value))
            continue

        for position, column in enumerate(member_columns(cells)):

            builder = RowBuilder("income_sources", sheet, row_number)
            builder.set("name", str(source.value) if position == 0 else f"{source.value} ({column.title()})")
            builder.put("source_type", source)
            builder.put("amount", cells.get(column))
            builder.set("frequency", frequency)
            keep(builder, context)

    if skipped:
        return SheetNote(sheet.name, "imported", f"Deduction lines not imported: {', '.join(skipped)}")

    return None


def read_expenses(
    sheet: Sheet,
    header: int,
    context: Context
    ) -> SheetNote | None:

    """One expense row per category and member; loan EMI lines are skipped, since the loans sheet already holds them."""

    frequency = "monthly" if monthly_title(sheet) else None
    skipped = []

    for row_number, cells in data_rows(sheet, header):

        category = cells.get("category")

        if category is None:
            continue

        section = cell_text(cells.get("section"))

        if "emi" in section.split() or "loan" in section:
            skipped.append(str(category.value))
            continue

        for position, column in enumerate(member_columns(cells)):

            builder = RowBuilder("expenses", sheet, row_number)
            builder.set("name", str(category.value) if position == 0 else f"{category.value} ({column.title()})")
            builder.put("category", category)
            builder.put("amount", cells.get(column))
            builder.set("frequency", frequency)
            builder.set("is_essential", section == "essential" if section else None)
            keep(builder, context)

    if skipped:
        return SheetNote(sheet.name, "imported", f"Loan EMI lines not imported, the loans sheet holds them: {', '.join(skipped)}")

    return None


def read_mutual_funds(
    sheet: Sheet,
    header: int,
    context: Context
    ) -> None:

    """One holding per fund line, plus a SIP row linked to it when a SIP amount is given."""

    for row_number, cells in data_rows(sheet, header):

        if cells.get("fund name") is None:
            continue

        builder = RowBuilder("holdings", sheet, row_number)
        builder.put("security_name", cells.get("fund name"))
        builder.put("plan_hint", cells.get("type"))
        builder.put("folio_number", cells.get("folio"))
        builder.put("units", cells.get("units"))
        builder.put("current_value", cells.get("current value"))
        builder.put("sip_amount", cells.get("sip amount"))
        builder.set("asset_type", "mutual_fund")
        builder.set("as_of_date", context.base_date)

        if not keep(builder, context):
            continue

        sip_amount = builder.row.data.pop("sip_amount", None)

        if sip_amount is None or sip_amount == "0.00":
            continue

        sip = RowBuilder("sip_plans", sheet, row_number)
        sip.put("amount", cells.get("sip amount"))
        sip.row.parent = builder.row
        context.rows.append(sip.row)


def read_stocks(
    sheet: Sheet,
    header: int,
    context: Context
    ) -> None:

    """One holding per stock line, with its ISIN."""

    for row_number, cells in data_rows(sheet, header):

        if cells.get("stock name") is None and cells.get("isin") is None:
            continue

        builder = RowBuilder("holdings", sheet, row_number)
        builder.put("security_name", cells.get("stock name"))
        builder.put("isin", cells.get("isin"))
        builder.put("units", cells.get("quantity"))
        builder.put("current_price", cells.get("current price"))
        builder.put("current_value", cells.get("current value"))
        builder.set("asset_type", "stock")
        builder.set("as_of_date", context.base_date)
        keep(builder, context)


def read_fixed_income(
    sheet: Sheet,
    header: int,
    context: Context
    ) -> None:

    """PPF, EPF, NPS and VPF lines become retirement accounts; FD and RD lines become deposits."""

    for row_number, cells in data_rows(sheet, header):

        instrument = cells.get("instrument")

        if instrument is None:
            continue

        try:
            pick_choice("retirement_account_type", instrument.value)
            retirement = True

        except NotReadable:
            retirement = False

        if retirement:

            builder = RowBuilder("retirement_accounts", sheet, row_number)
            builder.put("account_type", instrument)
            builder.put("balance", cells.get("current value"))
            builder.put("monthly_contribution", cells.get("monthly contribution"))
            builder.put("maturity_date", cells.get("maturity date"))
            builder.set("as_of_date", context.base_date)
            keep(builder, context)

            continue

        builder = RowBuilder("fixed_deposits", sheet, row_number)
        builder.put("deposit_type", instrument)
        builder.put("bank_name", cells.get("details"))
        builder.put("principal", cells.get("invested amount"))
        builder.put("monthly_contribution", cells.get("monthly contribution"))
        builder.put("current_value", cells.get("current value"))
        builder.put("maturity_date", cells.get("maturity date"))
        builder.put("maturity_amount", cells.get("maturity amount"))
        keep(builder, context)


def read_real_estate(
    sheet: Sheet,
    header: int,
    context: Context
    ) -> None:

    """One property per line, marked self-occupied when its type says so."""

    for row_number, cells in data_rows(sheet, header):

        kind = cells.get("property type")

        if kind is None:
            continue

        address = cells.get("address")

        builder = RowBuilder("physical_assets", sheet, row_number)
        builder.set("name", f"{kind.value} ({address.value})" if address is not None else str(kind.value))
        builder.put("asset_type", kind)
        builder.put("current_value", cells.get("current market value"))
        builder.put("loan_outstanding", cells.get("loan outstanding"))
        builder.set("is_self_occupied", "self occupied" in cell_text(kind))
        keep(builder, context)


def read_gold_others(
    sheet: Sheet,
    header: int,
    context: Context
    ) -> None:

    """One physical asset per line, typed from its description, falling back to other with a warning."""

    for row_number, cells in data_rows(sheet, header):

        description = cells.get("asset description")

        if description is None:
            continue

        builder = RowBuilder("physical_assets", sheet, row_number)
        builder.put("name", description)
        builder.put("current_value", cells.get("current value"))

        try:
            builder.set("asset_type", pick_choice("physical_asset_type", description.value))

        except NotReadable:
            builder.set("asset_type", "other")
            builder.warn(f"asset_type: '{description.value}' did not say gold, property or vehicle, so it is set to other")

        keep(builder, context)


def read_liquid(
    sheet: Sheet,
    header: int,
    context: Context
    ) -> SheetNote | None:

    """Bank balance lines become bank accounts; other lines, such as idle cash, are listed as not imported."""

    skipped = []

    for row_number, cells in data_rows(sheet, header):

        category = cells.get("category")

        if category is None:
            continue

        try:
            account_type = pick_choice("bank_account_type", category.value)

        except NotReadable:

            if cells.get("amount") is not None:
                skipped.append(str(category.value))

            continue

        builder = RowBuilder("bank_accounts", sheet, row_number)
        builder.set("account_type", account_type)
        builder.put("balance", cells.get("amount"))
        builder.set("as_of_date", context.base_date)
        keep(builder, context)

    if skipped:
        return SheetNote(sheet.name, "imported", f"Lines with no matching table, not imported: {', '.join(skipped)}")

    return None


def read_loans(
    sheet: Sheet,
    header: int,
    context: Context
    ) -> None:

    """One loan per line, with its outstanding amount, EMI, rate, tenure and end date."""

    for row_number, cells in data_rows(sheet, header):

        if cells.get("loan type") is None:
            continue

        builder = RowBuilder("loans", sheet, row_number)
        builder.put("loan_type", cells.get("loan type"))
        builder.put("outstanding", cells.get("outstanding amount"))
        builder.put("emi", cells.get("emi"))
        builder.put("interest_rate", cells.get("interest rate"))
        builder.put("tenure_months", cells.get("tenure"))
        builder.put("end_date", cells.get("end date"))
        keep(builder, context)


def read_insurance(
    sheet: Sheet,
    header: int,
    context: Context
    ) -> SheetNote | None:

    """One policy per line; a lone 'Status: ...' line means the sheet has no policies."""

    for row_number, cells in data_rows(sheet, header):

        text = first_text(cells)

        if text.lower().startswith("status:"):
            return SheetNote(sheet.name, "empty", f"Sheet found, but no rows ({text})")

        if cells.get("policy type") is None:
            continue

        builder = RowBuilder("insurance_policies", sheet, row_number)
        builder.put("policy_type", cells.get("policy type"))
        builder.put("policy_name", cells.get("coverage type"))
        builder.put("insurer", cells.get("company"))
        builder.put("cover_amount", cells.get("cover amount"))
        builder.put("premium", cells.get("annual premium"))
        builder.put("maturity_year", cells.get("maturity year"))
        builder.put("members_covered", cells.get("members covered"))
        builder.set("premium_frequency", "yearly")
        keep(builder, context)

    return None


def read_goals(
    sheet: Sheet,
    header: int,
    context: Context
    ) -> None:

    """One goal per line, with today's cost as the target amount, since the planner treats targets in today's money."""

    for row_number, cells in data_rows(sheet, header):

        if cells.get("name") is None:
            continue

        builder = RowBuilder("goals", sheet, row_number)
        builder.put("name", cells.get("name"))
        builder.put("goal_type", cells.get("category"))
        builder.put("priority", cells.get("importance"))
        builder.put("target_year", cells.get("target year"))
        builder.put("target_amount", cells.get("today's cost"))
        builder.put("future_value", cells.get("future value"))
        keep(builder, context)


def skip_with(message: str) -> Handler:

    """A rule for a known sheet that has no table to go to."""

    def handler(
        sheet: Sheet,
        header: int,
        context: Context
        ) -> SheetNote:

        """Report the sheet as not imported, with the reason."""

        return SheetNote(sheet.name, "not_imported", message)

    return handler


RULES = (
    SheetRule("personal", frozenset({"role", "name", "date of birth"}), read_personal),
    SheetRule("income", frozenset({"source", "is deduction"}), read_income),
    SheetRule("expenses", frozenset({"category", "section"}), read_expenses),
    SheetRule("mutual_funds", frozenset({"fund name", "folio", "units"}), read_mutual_funds),
    SheetRule("stocks", frozenset({"stock name", "isin", "quantity"}), read_stocks),
    SheetRule("fixed_income", frozenset({"instrument", "invested amount", "maturity date"}), read_fixed_income),
    SheetRule("real_estate", frozenset({"property type", "current market value"}), read_real_estate),
    SheetRule("gold_others", frozenset({"asset description", "current value"}), read_gold_others),
    SheetRule("liquid", frozenset({"category", "amount"}), read_liquid),
    SheetRule("loans", frozenset({"loan type", "outstanding amount", "emi"}), read_loans),
    SheetRule("insurance", frozenset({"policy type", "company", "cover amount"}), read_insurance),
    SheetRule("goals", frozenset({"name", "importance", "target year"}), read_goals),
    SheetRule("risk", frozenset({"question", "answer", "score"}), read_risk),
    SheetRule(
        "recurring",
        frozenset({"investment type", "monthly amount"}),
        skip_with("Sheet not imported: SIPs come from the mutual funds sheet, and these lines name no fund"),
        ),
    SheetRule(
        "future_changes",
        frozenset({"goal", "borrow"}),
        skip_with("Sheet not imported: future changes have no matching table yet"),
        ),
    )

TITLE_RULES = {
    "emergency fund": "Sheet not imported: the emergency fund has no matching table yet",
    "future changes": "Sheet not imported: future changes have no matching table yet",
    }


class PlannerWorkbook:

    """Reads the planner workbook, matching each sheet by its headers rather than its name."""

    name = FAMILY

    def match_rule(self, sheet: Sheet) -> tuple[SheetRule, int] | None:

        """The rule whose headers this sheet holds, and the header row, or None."""

        for rule in RULES:

            header = find_header(sheet, set(rule.headers))

            if header is not None:
                return rule, header

        return None

    def matches(self, sheets: list[Sheet]) -> bool:

        """Whether enough sheets look like the planner workbook to treat the whole file as one."""

        return sum(1 for sheet in sheets if self.match_rule(sheet) is not None) >= MIN_MATCHED_SHEETS

    def parse(self, sheets: list[Sheet]) -> ParseResult:

        """Read every sheet by its rule, putting the profile sheet first so its plan date reaches the holdings."""

        context = Context(base_date=find_base_date(sheets))
        notes = []
        matched = [(sheet, self.match_rule(sheet)) for sheet in sheets]
        matched.sort(key=lambda pair: 0 if pair[1] and pair[1][0].name == "personal" else 1)

        for sheet, found in matched:

            notes.append(self.read_sheet(sheet, found, context))

        order = {sheet.name: position for position, sheet in enumerate(sheets)}
        notes.sort(key=lambda note: order[note.sheet])

        if context.base_date is None and any(row.target_table in ("holdings", "bank_accounts") for row in context.rows):
            notes.append(SheetNote("", "warning", "No plan base date was found, so holdings and balances have no as-of date"))

        return ParseResult(rows=context.rows, notes=notes)

    def read_sheet(
        self,
        sheet: Sheet,
        found: tuple[SheetRule, int] | None,
        context: Context
        ) -> SheetNote:

        """Run one sheet's rule and describe what came of it."""

        if sheet.hidden:
            return SheetNote(sheet.name, "not_imported", "Hidden sheet, not imported")

        if found is None:
            return SheetNote(sheet.name, "not_imported", title_reason(sheet))

        rule, header = found
        before = len(context.rows)
        note = rule.handler(sheet, header, context)
        added = len(context.rows) - before

        if note is not None:
            note.rows = note.rows or added

            return note

        if added == 0:
            return SheetNote(sheet.name, "empty", "Sheet found, but no rows")

        return SheetNote(sheet.name, "imported", f"{added} rows read", added)


def title_reason(sheet: Sheet) -> str:

    """Why a sheet with no known headers was skipped, using its title when it names a known section."""

    title = " ".join(header_key(value) for value in sheet.row_values(0) if value is not None) if sheet.rows else ""

    for words, message in TITLE_RULES.items():

        if words in title:
            return message

    return "Sheet not imported: its headers do not match any section of this workbook"


def find_base_date(sheets: list[Sheet]) -> str | None:

    """The 'Plan base date' value from near the top of any sheet, as YYYY-MM-DD."""

    for sheet in sheets:

        for index in range(min(len(sheet.rows), 10)):

            values = [value for value in sheet.row_values(index) if value is not None]

            if len(values) >= 2 and header_key(values[0]).startswith(BASE_DATE_LABEL):

                try:
                    return to_date(values[1])

                except NotReadable:
                    return None

    return None
