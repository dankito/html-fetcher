from dataclasses import dataclass


@dataclass
class AppConfig:
    port: int = 3330
    root_path: str = ""

    camoufox_data_dir: str | None = None
    
    use_zendriver: bool = True
    zendriver_data_dir: str | None = None

    version: str = "unknown"
    commit_id: str | None = None