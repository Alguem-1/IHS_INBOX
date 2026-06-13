"""
config.py — Configuração própria do IHS_INBOX, em ~/.ihs_inbox/config.json.
Independente do IHS_UTILS, mas reaproveita o server_url/usuário do cliente do
UTILS (~/.ihs_utils/client_config.json) como PADRÃO (só leitura).
"""

import json
from pathlib import Path

_CONFIG_DIR = Path.home() / ".ihs_inbox"
_CONFIG_PATH = _CONFIG_DIR / "config.json"

# Config do cliente do IHS_UTILS — lida SÓ p/ herdar server_url/usuário padrão.
_UTILS_CONFIG_PATH = Path.home() / ".ihs_utils" / "client_config.json"

DEFAULT_LIBRARY_ROOT = str(Path.home() / "IHS-Biblioteca")


def load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_library_root() -> str | None:
    return load_config().get("library_root")


def set_library_root(path: str) -> None:
    data = load_config()
    data["library_root"] = str(Path(path).expanduser())
    _save(data)


def _load_utils_config() -> dict:
    if not _UTILS_CONFIG_PATH.exists():
        return {}
    try:
        with open(_UTILS_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def get_utils_server_url() -> str:
    """server_url do INBOX; se não houver, herda o do cliente do UTILS."""
    cfg = load_config()
    if cfg.get("utils_server_url"):
        return cfg["utils_server_url"]
    return _load_utils_config().get("server_url", "")


def get_utils_last_username() -> str:
    cfg = load_config()
    if cfg.get("utils_last_username"):
        return cfg["utils_last_username"]
    return _load_utils_config().get("last_username", "")


def save_utils_login(server_url: str, username: str) -> None:
    """Lembra o último servidor/usuário do UTILS usado pelo INBOX (sem token)."""
    data = load_config()
    data["utils_server_url"] = server_url.rstrip("/")
    data["utils_last_username"] = username
    _save(data)
