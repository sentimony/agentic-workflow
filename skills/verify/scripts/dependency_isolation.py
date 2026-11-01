"""Prepare private writable paths; this is an environment recipe, not a sandbox."""
import os
from pathlib import Path


PRIVATE_PATHS = {
    "HOME": "home",
    "XDG_CONFIG_HOME": "config",
    "XDG_DATA_HOME": "data",
    "XDG_CACHE_HOME": "cache",
    "TMPDIR": "tmp",
    "TMP": "tmp",
    "TEMP": "tmp",
    "npm_config_cache": "npm-cache",
    "npm_config_prefix": "npm-prefix",
    "UV_CACHE_DIR": "uv-cache",
    "PIP_CACHE_DIR": "pip-cache",
    "PYTHONPYCACHEPREFIX": "pycache",
    "CARGO_HOME": "cargo",
    "GRADLE_USER_HOME": "gradle",
}


def prepare_environment(root, tool_path):
    """Create a fresh private root and return an allowlisted child environment.

    The caller inventories project-specific writes and supplies a reviewed PATH.
    No inherited settings, credentials, agent CLIs or shared caches are added.
    Existing roots are refused, so stale paths or links cannot be reused silently.
    """
    root = Path(root).absolute()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    env = {"PATH": str(tool_path), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "PYTHONNOUSERSITE": "1"}
    for name, relative in PRIVATE_PATHS.items():
        path = root / relative
        path.mkdir(mode=0o700, exist_ok=True)
        env[name] = str(path)
    return env
