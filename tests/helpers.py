"""Small fakes so tests don't depend on Hindsight's full request/context plumbing."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock


@dataclass
class FakeRequestContext:
    """Stand-in for hindsight_api.models.RequestContext (only api_key is read)."""

    api_key: str | None = None


@dataclass
class FakeOpCtx:
    """Stand-in for RetainContext / BankWriteContext (validator reads these fields)."""

    bank_id: str
    request_context: FakeRequestContext
    operation: str = "retain"
    contents: list = field(default_factory=list)


class FakeExtensionContext:
    """Stand-in for ExtensionContext — records run_migration calls."""

    def __init__(self) -> None:
        self.run_migration = AsyncMock()
