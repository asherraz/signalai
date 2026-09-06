"""Audit records for deterministic legacy-data migrations."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from signalai.schemas.models import NonEmptyText, SignalModel, _require_timezone


class MigrationSourceSummary(SignalModel):
    source_file: NonEmptyText
    source_sha256: str
    source_record_counts: dict[str, int]
    imported_record_counts: dict[str, int]
    mapped_fields: list[str] = Field(default_factory=list)
    unmapped_fields: list[str] = Field(default_factory=list)
    mapping_notes: list[str] = Field(default_factory=list)


class LegacyMigrationReport(SignalModel):
    migration_id: NonEmptyText
    generated_at: datetime
    sources: list[MigrationSourceSummary]

    @model_validator(mode="after")
    def validate_generated_at(self) -> LegacyMigrationReport:
        object.__setattr__(
            self, "generated_at", _require_timezone(self.generated_at, "generated_at")
        )
        return self
