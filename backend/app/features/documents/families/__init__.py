"""The known file families and the check that picks exactly one of them for a file, or none."""

from typing import Protocol

from app.features.documents.families.planner_workbook import PlannerWorkbook
from app.features.documents.parsing import ParseResult
from app.features.documents.reader import Sheet


class Family(Protocol):

    """A file format the code reads with fixed rules and no model."""

    name: str

    def matches(self, sheets: list[Sheet]) -> bool:

        """Whether this file is of this family."""

        ...

    def parse(self, sheets: list[Sheet]) -> ParseResult:

        """Read the file into rows and sheet notes."""

        ...


class TooManyFamilies(ValueError):

    """A file whose headers fit more than one family, so no parser can be trusted to read it."""


FAMILIES: tuple[Family, ...] = (PlannerWorkbook(),)


def classify(sheets: list[Sheet]) -> Family | None:

    """The one family that fits the file, None when none does, and an error when two do."""

    found = [family for family in FAMILIES if family.matches(sheets)]

    if len(found) > 1:
        raise TooManyFamilies(f"This file matches more than one format: {', '.join(family.name for family in found)}")

    return found[0] if found else None
