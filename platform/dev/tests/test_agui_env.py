"""agent.env.j2: the L5 airlock switch. Off, the file is byte-identical to the one before the switch existed
(decision 3), so an instance without it keeps today's agent container."""
from pathlib import Path

import jinja2
import pytest
import yaml

TEMPLATE = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "agui" / "templates" / "agent.env.j2"
BASE = {"spe_agent_api_key": "agent-key", "spe_terminal_api_key": "terminal-key",
        "spe_agent_model_provider": "openai_compatible", "spe_agent_llm_key": "llm-key\n",
        "spe_study_id_prefix": "STUDY"}
BEFORE = ("# Managed by spe-ansible (role: agui). Only the agent container receives this file.\n"
          "SPE_AGENT_API_KEY=agent-key\nSANDBOX_API_KEY=terminal-key\nOPENAI_API_KEY=llm-key\n")


def ansible_bool(value) -> bool:
    """Ansible's `bool` filter, for the values an instance file or `-e` can give."""
    return value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on", "y")


def render(**over) -> str:
    # The settings Ansible's template module uses: trim_blocks on, the trailing newline kept.
    env = jinja2.Environment(trim_blocks=True, keep_trailing_newline=True, undefined=jinja2.StrictUndefined)
    env.filters["bool"] = ansible_bool
    return env.from_string(TEMPLATE.read_text()).render(**{**BASE, **over})


@pytest.mark.parametrize("off", [False, "false", "False"])
def test_off_renders_byte_identical_to_before(off):
    assert render(spe_harden_airlock=off) == BEFORE


@pytest.mark.parametrize("on", [True, "true"])
def test_on_adds_the_switch_and_the_prefix(on):
    out = render(spe_harden_airlock=on, spe_study_id_prefix="TRIAL")
    assert out.startswith(BEFORE)
    comment, *lines = out[len(BEFORE):].splitlines()
    assert comment.startswith("# L5 airlock") and lines == ["SPE_AIRLOCK=1", "SPE_STUDY_ID_PREFIX=TRIAL"]


CREATE = TEMPLATE.parents[3] / "playbooks" / "create.yml"


def instance_accepted(**v) -> bool:
    """create.yml's first check (*Instance parameters present*), evaluated as Ansible would."""
    play = yaml.safe_load(CREATE.read_text())[0]
    task = next(t for t in play["pre_tasks"] if t["name"] == "Instance parameters present")
    env = jinja2.Environment()
    env.filters["bool"] = ansible_bool
    env.filters["difference"] = lambda a, b: [x for x in a if x not in b]
    v = {"spe_instance": "t-01", "spe_seed": 1, "spe_provision": "existing", **v}
    return all(env.compile_expression(c)(**v) for c in task["ansible.builtin.assert"]["that"])


def test_create_refuses_the_airlock_with_open_webui():
    assert instance_accepted(spe_frontends=["agui"], spe_harden_airlock=True)
    assert instance_accepted(spe_frontends=["openwebui", "agui"], spe_harden_airlock="false")
    assert not instance_accepted(spe_frontends=["openwebui", "agui"], spe_harden_airlock=True)
