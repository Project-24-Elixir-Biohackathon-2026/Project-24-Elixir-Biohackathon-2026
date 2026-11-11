"""The guide and the index stay complete as commands and experiments are added (experiments spec
part 07, decision 19's acceptance checks):

  - `platform/instance/workspace/AGENTS.md`'s *Experiments* section names every `spe-eval`
    subcommand (from `spe-eval --help`, never a hand-kept list: a future subcommand fails this
    test until the guide names it) and `check_experiment.py`;
  - `experiments/README.md` indexes every `experiments/*.yml` (`TEMPLATE.yml` excluded, same as
    `check_experiment.py` and the template itself).
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SPE_EVAL = REPO / "platform" / "instance" / "spe-eval"
WORKSPACE_AGENTS = REPO / "platform" / "instance" / "workspace" / "AGENTS.md"
EXPERIMENTS_README = REPO / "experiments" / "README.md"
EXPERIMENTS_DIR = REPO / "experiments"


def spe_eval_subcommands() -> list[str]:
    """The subcommand names argparse itself knows, read from `spe-eval --help`'s usage line
    (`usage: spe-eval [-h] {new,test,arm,...} ...`) rather than duplicated here."""
    result = subprocess.run([sys.executable, str(SPE_EVAL), "--help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    match = re.search(r"\{([a-z,-]+)\}", result.stdout)
    assert match, f"could not find the subcommand list in:\n{result.stdout}"
    return match.group(1).split(",")


def experiments_section() -> str:
    text = WORKSPACE_AGENTS.read_text()
    match = re.search(r"\n## Experiments\b.*?(?=\n## |\Z)", text, re.S)
    assert match, "platform/instance/workspace/AGENTS.md has no *Experiments* section"
    return match.group(0)


def _word_present(word: str, text: str) -> bool:
    """`word` appears in `text` with no letter, digit, underscore or hyphen touching either end: a
    plain substring match lets a shorter name hide behind a longer one that merely starts the same
    way ('run' inside 'runs', 'ladder' inside 'ladder-l0'), and a bare `\\b` does not catch the
    hyphen case (a word boundary sits on both sides of it already)."""
    return re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text) is not None


def test_guide_names_every_spe_eval_subcommand():
    section = experiments_section()
    subcommands = spe_eval_subcommands()
    assert subcommands, "spe-eval --help reported no subcommands"
    missing = [cmd for cmd in subcommands if not _word_present(f"spe-eval {cmd}", section)]
    assert not missing, f"workspace AGENTS.md's *Experiments* section is missing: {missing}"


def test_guide_names_check_experiment():
    section = experiments_section()
    assert "check_experiment.py" in section, \
        "workspace AGENTS.md's *Experiments* section does not mention check_experiment.py"


def test_every_experiment_file_is_indexed_in_readme():
    readme = EXPERIMENTS_README.read_text()
    names = sorted(p.stem for p in EXPERIMENTS_DIR.glob("*.yml") if p.stem != "TEMPLATE")
    assert names, "experiments/ has no experiment files to check against"
    missing = [name for name in names if not _word_present(name, readme)]
    assert not missing, f"experiments/README.md has no line for: {missing}"
