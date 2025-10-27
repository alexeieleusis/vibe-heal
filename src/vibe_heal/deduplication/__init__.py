"""Deduplication module for removing duplicate code."""

from vibe_heal.deduplication.models import (
    DuplicationBlock,
    DuplicationFileInfo,
    DuplicationGroup,
    DuplicationsResponse,
)
from vibe_heal.deduplication.orchestrator import (
    DedupeBranchOrchestrator,
    DedupeBranchResult,
    DeduplicationOrchestrator,
    FileDedupResult,
)

__all__ = [
    "DedupeBranchOrchestrator",
    "DedupeBranchResult",
    "DeduplicationOrchestrator",
    "DuplicationBlock",
    "DuplicationFileInfo",
    "DuplicationGroup",
    "DuplicationsResponse",
    "FileDedupResult",
]
