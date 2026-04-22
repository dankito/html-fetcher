import os

from src.model.app_config import AppConfig


class AppConfigParser:

    def parse_app_config(self) -> AppConfig:
        return AppConfig(
            port=self._int("PORT", 3330),
            root_path=self._str("ROOT_PATH", ""),

            camoufox_data_dir=self._str_or_none("CAMOUFOX_DATA_DIR"),

            use_zendriver=self._bool_default_true("USE_ZENDRIVER"),
            zendriver_data_dir=self._str_or_none("ZENDRIVER_DATA_DIR"),
        )


    def _str(self, key: str, default: str) -> str:
        return self._str_or_none(key) or default

    def _str_or_none(self, key: str, default: str | None = None) -> str | None:
        return os.environ.get(key, default)

    def _int(self, key: str, default: int) -> int:
        return int(self._str_or_none(key) or default)

    def _bool_default_true(self, key: str) -> bool:
        env_value = self._str_or_none(key)
        if env_value is None or env_value == "" or env_value.isspace():
            return True
        else:
            return env_value.lower() not in (
                "0",
                "false",
                "no",
            )