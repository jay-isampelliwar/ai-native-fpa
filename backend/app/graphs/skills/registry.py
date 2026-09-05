"""The one place a skill name becomes a runnable, policy carrying skill.

The router produces a string. Nothing downstream may act on that string directly,
because a model chosen name is untrusted input: it can be misspelled, hallucinated or
injected through imported statement text. ``SkillRegistry.resolve`` is the gate that
turns it into a ``SkillDefinition`` plus an implementation, or refuses.

Registration is explicit and happens at import time. There is no filesystem scan and no
dynamic import by name, so the set of reachable skills is exactly what the code says it
is - an attacker who controls the routed name still cannot reach anything unregistered.

Versions are first class. ``resolve`` without a version returns the enabled version for
that name, and a skill is looked up by ``(name, version)`` everywhere else, so an audit
record written six months ago still names the exact implementation that produced it.
Disabling a version is the rollback switch: it stays registered and auditable but stops
being resolvable, which is safer than deleting it.
"""

from app.graphs.skills.contracts import FinancialSkill, SkillDefinition


class SkillNotFoundError(Exception):

    """Raised when a routed skill name has no registered, enabled version."""


class SkillRegistry:

    """Holds every registered skill version and resolves a routed name to one of them."""

    def __init__(self) -> None:

        """Start empty, expecting explicit registration at application import time."""

        self._skills: dict[tuple[str, str], tuple[SkillDefinition, FinancialSkill]] = {}
        self._enabled: dict[str, str] = {}

    def register(
        self,
        definition: SkillDefinition,
        skill: FinancialSkill,
        enabled: bool = True,
        ) -> None:

        """Add one skill version, optionally making it the version new requests resolve to."""

        self._skills[(definition.name, definition.version)] = (definition, skill)

        if enabled:
            self._enabled[definition.name] = definition.version

    def resolve(
        self,
        name: str,
        version: str | None = None,
        ) -> tuple[SkillDefinition, FinancialSkill]:

        """Turn an untrusted routed name into a definition and implementation, or refuse."""

        resolved_version = version or self._enabled.get(name)

        if resolved_version is None:
            raise SkillNotFoundError(f"no enabled version registered for skill {name!r}")

        entry = self._skills.get((name, resolved_version))

        if entry is None:
            raise SkillNotFoundError(f"skill {name!r} version {resolved_version!r} is not registered")

        return entry

    def routable_names(self) -> list[str]:

        """List the enabled skill names, which is the closed choice set given to the router."""

        return sorted(self._enabled)


registry = SkillRegistry()
