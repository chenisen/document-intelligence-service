"""Value objects shared across the domain.

These carry only the invariant that makes the type a type. Business rules that belong to a specific
document field, such as CRM format or CID membership, arrive with slice 3.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Confidence:
    """How much the service trusts a value, from 0 to 1.

    Composed later from OCR confidence, model confidence and the deterministic validations. A bare
    float would let 7.2 through, and a confidence of 7.2 is not a confidence.
    """

    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"confidence must be between 0 and 1, got {self.value}")

    def below(self, threshold: float) -> bool:
        return self.value < threshold


@dataclass(frozen=True)
class Evidence:
    """The literal excerpt of recognised text a value came from, and the page it was found on.

    Verifying that this excerpt really exists in the source text is the cheapest defence against
    hallucination, and it lands in slice 3 as RF-20.
    """

    text: str
    page: int

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("evidence text cannot be empty")
        if self.page < 1:
            raise ValueError(f"page numbering starts at 1, got {self.page}")
