from dataclasses import dataclass


@dataclass(frozen=True)
class Confidence:
    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"confidence must be between 0 and 1, got {self.value}")

    def below(self, threshold: float) -> bool:
        return self.value < threshold


@dataclass(frozen=True)
class Evidence:
    text: str
    page: int

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("evidence text cannot be empty")
        if self.page < 1:
            raise ValueError(f"page numbering starts at 1, got {self.page}")
