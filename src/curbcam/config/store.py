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

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import PydanticBaseSettingsSource

from curbcam.config.schema import Settings


class _DictSettingsSource(PydanticBaseSettingsSource):
    """A pydantic-settings source backed by a plain dict.

    Used to feed YAML-loaded values into the settings priority chain
    at a position *below* ``EnvSettingsSource``, so environment variables
    always override persisted YAML values.
    """

    def __init__(self, settings_cls: type[Settings], data: dict[str, Any]) -> None:
        super().__init__(settings_cls)
        self._data = data

    def get_field_value(
        self, field: Any, field_name: str
    ) -> tuple[Any, str, bool]:  # pragma: no cover
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return self._data


def _settings_from_yaml_dict(data: dict[str, Any]) -> Settings:
    """Construct a Settings instance with correct source priority.

    Priority (highest → lowest):
        1. Environment variables  (EnvSettingsSource)
        2. Persisted YAML dict    (_DictSettingsSource)
        3. Field defaults         (implicit in model)

    This ensures ``CURBCAM_*`` env vars always win over whatever is
    stored in the YAML file.
    """
    yaml_source = _DictSettingsSource(Settings, data)

    class _SettingsWithYaml(Settings):
        @classmethod
        def settings_customise_sources(  # type: ignore[override]
            cls,
            settings_cls: type[Settings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            # Drop init_settings so caller kwargs cannot sneak in.
            return env_settings, dotenv_settings, file_secret_settings, yaml_source

    instance = _SettingsWithYaml()
    # Return a plain Settings so callers never see the subclass.
    return Settings.model_validate(instance.model_dump())


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    @staticmethod
    def _defaults_without_env() -> Settings:
        """Construct Settings from field defaults ONLY, ignoring CURBCAM_* env
        vars, so first-run/raw defaults never leak env-only credentials (e.g.
        CURBCAM_CAMERA__SOURCE=rtsp://user:pw@...) into the on-disk YAML."""
        env_snapshot = {k: v for k, v in os.environ.items() if k.startswith("CURBCAM_")}
        try:
            for k in env_snapshot:
                del os.environ[k]
            return Settings()
        finally:
            os.environ.update(env_snapshot)

    def load(self) -> Settings:
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Write pure defaults WITHOUT env overlay (see _defaults_without_env),
            # then return an env-overlaid Settings for the caller.
            self._write_yaml(self._defaults_without_env().model_dump(mode="json"))
            return Settings()

        with self._path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return _settings_from_yaml_dict(data)

    def save(self, settings: Settings) -> None:
        self._write_yaml(settings.model_dump(mode="json"))

    def load_raw(self) -> dict[str, Any]:
        """Return the YAML dict as-on-disk, WITHOUT env-var overlay.

        Used by the settings UI so saving never bakes an env-shadowed
        value into the file (spec §5). Returns defaults if the file is
        absent.
        """
        if not self._path.exists():
            return self._defaults_without_env().model_dump(mode="json")
        with self._path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
            return data

    def save_raw(self, data: dict[str, Any]) -> None:
        self._write_yaml(data)

    def _write_yaml(self, data: dict[str, Any]) -> None:
        with self._path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, indent=2)
