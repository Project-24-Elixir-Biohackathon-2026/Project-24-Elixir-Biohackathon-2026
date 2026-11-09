"""Render an Ansible role template offline, with the options of Ansible's template module."""
import ast
from pathlib import Path

import jinja2
import yaml

ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
GOLDEN = Path(__file__).resolve().parent / "golden"

# Values Ansible sets at run time (facts, set_fact, role results) that templates read.
RUNTIME = {
    "spe_instance": "ladder-test", "spe_seed": 1234, "spe_api_host": "10.0.2.245",
    "spe_floating_ip": None, "spe_weskit_image": "weskit:test", "spe_svc_token_wes": "SVC-TEST",
    "agui_ui_image": "spe-chat-ui:test", "agui_agent_image": "spe-agent:test",
    "agui_config_hash": "0" * 64, "playbook_dir": "/repo/platform/ansible/playbooks",
}


def ansible_bool(value) -> bool:
    """Ansible's `bool` filter, for the values an instance file or `-e` can give."""
    return value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on", "y")


def environment(templates: Path | None = None) -> jinja2.Environment:
    loader = jinja2.FileSystemLoader(str(templates)) if templates else None
    env = jinja2.Environment(loader=loader, trim_blocks=True, keep_trailing_newline=True,
                             undefined=jinja2.StrictUndefined)
    env.filters["bool"] = ansible_bool  # frontend.env.j2 and the switches use it
    return env


def _native(text: str):
    """A rendered list or dict back to Python, as Ansible does (spe_frontends, spe_compose_overlays)."""
    if text.strip()[:1] in ("[", "{"):
        try:
            return ast.literal_eval(text.strip())
        except (ValueError, SyntaxError):
            pass
    return text


def load_vars(**overrides) -> dict:
    v = yaml.safe_load((ANSIBLE / "inventory" / "group_vars" / "all.yml").read_text())
    v.update(RUNTIME)
    v.update(overrides)
    env = environment()
    for _ in range(5):  # resolve defaults like "{{ spe_stack_dir }}/certs", as Ansible does lazily
        changed = False
        for k, val in list(v.items()):
            if k in overrides or not isinstance(val, str) or "{{" not in val:
                continue
            try:
                new = _native(env.from_string(val).render(v))
            except Exception:  # Ansible-only filters and lookups stay literal
                continue
            if new != val:
                v[k], changed = new, True
        if not changed:
            break
    return v


def render(role: str, template: str, **overrides) -> str:
    env = environment(ANSIBLE / "roles" / role / "templates")
    return env.get_template(template).render(load_vars(**overrides))
