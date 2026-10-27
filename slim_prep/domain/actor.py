"""Who does something (P-17). slim-prep never authenticates; the host passes an Actor in, with the
roles it gave the person."""

from enum import IntEnum

from pydantic import Field

from slim_prep.domain.base import Frozen


class Role(IntEnum):
    ANALYST = 1
    SUPERVISOR = 2
    QUALITY = 3  # the quality manager: publishes the prep rules (P-17)


class Actor(Frozen):
    id: str = Field(min_length=1, max_length=100)
    display: str = Field(min_length=1, max_length=254)
    roles: frozenset[Role] = frozenset()

    @property
    def may_publish_rules(self) -> bool:
        """Quality sets the rules (P-17); a supervisor stands in until the host has a quality role."""
        return bool(self.roles & {Role.QUALITY, Role.SUPERVISOR})
