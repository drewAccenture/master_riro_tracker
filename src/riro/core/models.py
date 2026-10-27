"""Plain dataclasses shared by all layers."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HeaderReport:
    """Slice 1 header check of one checklist file (architecture section 10)."""

    sheet_name: str
    sheet_matched: bool  # True if chosen because its name has "roll-in" or "rollin"
    headers_found: tuple[str, ...]
    headers_missing: tuple[str, ...]
    row_count: int
    deadline_counts: dict[str, int] = field(default_factory=dict)
    status_counts: dict[str, int] = field(default_factory=dict)
