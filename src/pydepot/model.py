from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import __version__


FORMAT_VERSION = 1


@dataclass(frozen=True)
class Artifact:
    filename: str
    sha256: str
    size: int
    name: str | None = None
    version: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Artifact":
        return cls(
            filename=str(value["filename"]),
            sha256=str(value["sha256"]),
            size=int(value["size"]),
            name=value.get("name"),
            version=value.get("version"),
        )


@dataclass
class Manifest:
    python_version: str
    implementation: str
    platforms: list[str]
    abis: list[str]
    requested: list[str]
    artifacts: list[Artifact] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    format_version: int = FORMAT_VERSION
    created_by: str = f"pydepot/{__version__}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Manifest":
        version = int(value.get("format_version", 0))
        if version != FORMAT_VERSION:
            from .errors import BundleError

            raise BundleError(
                f"Version de bundle non prise en charge: {version} "
                f"(attendue: {FORMAT_VERSION})."
            )
        return cls(
            python_version=str(value["python_version"]),
            implementation=str(value.get("implementation", "cp")),
            platforms=[str(item) for item in value.get("platforms", [])],
            abis=[str(item) for item in value.get("abis", [])],
            requested=[str(item) for item in value.get("requested", [])],
            artifacts=[Artifact.from_dict(item) for item in value.get("artifacts", [])],
            created_at=str(value["created_at"]),
            format_version=version,
            created_by=str(value.get("created_by", "unknown")),
        )

