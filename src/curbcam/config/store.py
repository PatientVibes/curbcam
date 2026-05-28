"""Load and save Settings as YAML.

Behaviour:
- ``load()`` reads the YAML if present (creates with defaults if not),
  then constructs ``Settings``. Pydantic-settings overlays env vars on
  top of the YAML at construction time, so the returned instance is
  YAML ⊕ env.
- ``save(s)`` writes the in-memory values to YAML as-is. If an env var
  was overriding a field at save time, that env value is what gets
  persisted — MVP-1 does not try to be clever about this. MVP-2's
  settings UI will accept user-typed form values and call save() with
  those, sidestepping the problem.
"""

from pathlib import Path

import yaml

from curbcam.config.schema import Settings


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Settings:
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            default = Settings()
            self._write_yaml(default.model_dump(mode="json"))
            return default

        with self._path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return Settings.model_validate(data)

    def save(self, settings: Settings) -> None:
        self._write_yaml(settings.model_dump(mode="json"))

    def _write_yaml(self, data: dict) -> None:  # type: ignore[type-arg]
        with self._path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, indent=2)
