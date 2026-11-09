"""Entry point: python -m spe_agent. Configuration from SPE_AGENT_CONFIG, keys from the environment."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn

from .airlock import AirlockConfigError, settings as airlock_settings
from .app import create_app
from .config import ConfigError, load_config, load_secrets


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per sandbox request and probe otherwise
    path = Path(os.environ.get("SPE_AGENT_CONFIG", "/etc/spe-agent/agent.yaml"))
    try:
        config = load_config(path)
        app = create_app(config, load_secrets(config, os.environ), airlock_prefix=airlock_settings(os.environ))
    except (ConfigError, AirlockConfigError) as e:
        print(f"spe-agent: {e}", file=sys.stderr)
        return 2
    host, port = os.environ.get("SPE_AGENT_HOST", "0.0.0.0"), int(os.environ.get("SPE_AGENT_PORT", "8100"))
    if os.environ.get("SPE_AGENT_RELOAD") == "1":
        # Development: the source is a bind mount; a saved .py file restarts the server. uvicorn
        # needs an import string for that, so the app is rebuilt by the new process (see app_factory).
        src = str(Path(__file__).resolve().parent.parent)
        uvicorn.run("spe_agent.__main__:app_factory", factory=True, reload=True, reload_dirs=[src],
                    host=host, port=port, server_header=False, proxy_headers=False, access_log=True)
        return 0
    uvicorn.run(app, host=host, port=port, server_header=False, proxy_headers=False, access_log=True)
    return 0


def app_factory():
    """The app for uvicorn's reloader: configuration and keys as in main(), errors are fatal."""
    path = Path(os.environ.get("SPE_AGENT_CONFIG", "/etc/spe-agent/agent.yaml"))
    try:
        config = load_config(path)
        return create_app(config, load_secrets(config, os.environ), airlock_prefix=airlock_settings(os.environ))
    except (ConfigError, AirlockConfigError) as e:
        sys.exit(f"spe-agent: {e}")


if __name__ == "__main__":
    sys.exit(main())
