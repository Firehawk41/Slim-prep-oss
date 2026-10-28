"""Why the domain refuses something: every problem at once, each with where it is."""

from slim_prep.domain.base import Frozen


class Problem(Frozen):
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.where}: {self.message}" if self.where else self.message


class PrepRefused(ValueError):
    def __init__(self, problems: list[Problem]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(str(p) for p in problems))
