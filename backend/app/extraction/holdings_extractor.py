"""Reading a holdings workbook, by a template if one fits and by asking for a mapping if none does.

The order of attempts is the design. A template a person confirmed for this exact layout wins, because
it is the most specific thing available and someone already judged it. Failing that, the built in
families are tried, and a family is accepted only if it actually produced rows - a template that
matches a sheet name but finds no instrument column has not understood the file and should not claim it.

Failing both, the file is not guessed at. It comes back with ``needs_mapping`` and the layout it found,
which becomes a mapping proposal a person confirms once. Guessing would produce holdings that look
plausible and are wrong, and a wrong holdings row is a wrong portfolio value in every answer afterwards.

Statement totals are read whichever path parsed the file, because reconciliation is the check that
catches what row level confidence cannot: a whole sheet skipped, a column mapped to the wrong field, or
a total row imported as a holding. A file that parses cleanly and reconciles to the rupee is a
different level of evidence from one that merely parses.

The as of date is taken from the filename or the sheet when it is stated and left unset when it is not.
A holdings statement is a snapshot, and dating it wrongly is worse than admitting the date is unknown.

Nothing here writes. Rows are staged with their sheet, row number and original cells, so a figure that
looks wrong later can be traced to the line it came from.
"""

import asyncio

import re
from datetime import date

from app.extraction.base import ExtractedRow, ExtractionResult
from app.extraction.builtin_templates import BUILTIN_TEMPLATES
from app.extraction.holdings import to_payload
from app.extraction.sheets import read_without_a_template
from app.extraction.templates import TemplateSpec, parse_with_template
from app.extraction.workbook import open_workbook
from app.extraction.values import to_date

WORKBOOK_SUFFIXES = (".xlsx", ".xlsm")

WORKBOOK_CONTENT_TYPES = (
    "spreadsheetml",
    "application/vnd.ms-excel",
    "application/octet-stream",
)

DATE_IN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})")


def as_of_from(filename: str, sheets: dict[str, list[list]]) -> date | None:

    """Take the snapshot date from the filename or a stated one in the sheet, or admit it is unknown."""

    match = DATE_IN_NAME.search(filename)

    if match:
        parsed = to_date(match.group(1))

        if parsed:
            return parsed

    for rows in sheets.values():

        for row in rows[:20]:

            for value in row:

                text = str(value) if value is not None else ""

                if "as on" in text.lower() or "as of" in text.lower():

                    for token in re.split(r"as on|as of", text, flags=re.IGNORECASE)[-1:]:
                        parsed = to_date(token.strip().strip(".,"))

                        if parsed:
                            return parsed

    return None


class HoldingsWorkbookExtractor:

    """Extracts holdings from a spreadsheet, by a confirmed template, a built in family, or not at all."""

    name = "holdings_workbook.v1"

    def can_handle(self, filename: str, content_type: str, head: bytes) -> bool:

        """Claim any spreadsheet, since which provider it is from is decided after the layout is read."""

        if filename.lower().endswith(WORKBOOK_SUFFIXES):
            return True

        return any(marker in content_type for marker in WORKBOOK_CONTENT_TYPES) and head[:2] == b"PK"

    async def extract(
        self,
        content: bytes,
        filename: str,
        user_id: int,
        password: str | None = None,
        ) -> ExtractionResult:

        """Read the workbook with the most specific template that fits, or ask for a mapping instead."""

        try:
            sheets, profile = await asyncio.to_thread(open_workbook, content)

        except Exception as exc:
            return ExtractionResult(
                extractor=self.name,
                detected_format="workbook",
                document_kind="holdings_statement",
                error=f"this workbook could not be opened: {type(exc).__name__}",
            )

        as_of = as_of_from(filename, sheets)

        template = await self.find_template(profile.fingerprint, user_id)

        if template is not None:
            return self.parse(template, sheets, as_of, profile.fingerprint)

        for candidate in BUILTIN_TEMPLATES:

            result = self.parse(candidate, sheets, as_of, profile.fingerprint)

            if result.rows:
                return result

        return await read_without_a_template(profile, sheets, self.name)

    async def find_template(self, fingerprint: str, user_id: int) -> TemplateSpec | None:

        """Look for a mapping this person already confirmed for this exact layout."""

        from app.repositories.templates_repository import templates_repository

        try:
            return await templates_repository.by_fingerprint(fingerprint, user_id)

        except Exception:
            return None

    def parse(
        self,
        template: TemplateSpec,
        sheets: dict[str, list[list]],
        as_of: date | None,
        fingerprint: str,
        ) -> ExtractionResult:

        """Apply one template and package what it produced, keeping each row's origin with it."""

        parsed, totals = parse_with_template(template, sheets, as_of=as_of)

        rows = [
            ExtractedRow(
                target_table="holdings",
                payload=to_payload(holding),
                confidence=holding.confidence,
                issue="; ".join(holding.issues) or None,
                source_sheet=sheet_name,
                source_row_number=row_number,
                source_cells=cells,
            )
            for sheet_name, row_number, cells, holding in parsed
        ]

        return ExtractionResult(
            extractor=self.name,
            detected_format=template.id,
            document_kind=template.document_kind,
            rows=rows,
            template_id=template.id,
            statement_totals=totals,
        )
