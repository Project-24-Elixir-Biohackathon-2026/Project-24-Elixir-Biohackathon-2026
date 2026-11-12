"""The entry points configure logging in the process that serves requests."""
import subprocess
import sys
import textwrap

# uvicorn's reloader serves from a fresh process that imports app_factory and never runs main():
# the agent's INFO lines must still reach the container log.
RELOAD_WORKER = textwrap.dedent("""
    import logging
    import spe_agent.__main__ as entry
    entry.load_config = lambda path: "config"
    entry.load_secrets = lambda config, environ: "secrets"
    entry.create_app = lambda config, secrets: "app"
    assert entry.app_factory() == "app"
    logging.getLogger("spe_agent.app").info("agent probe")
    logging.getLogger("httpx").info("httpx probe")
""")


def test_app_factory_logs_the_agents_info_lines_but_not_httpx():
    run = subprocess.run([sys.executable, "-c", RELOAD_WORKER], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    assert "INFO spe_agent.app: agent probe" in run.stderr
    assert "httpx probe" not in run.stderr
