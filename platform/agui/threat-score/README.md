# Threat score

A classifier on prompt embeddings that says how much a prompt resembles known adversarial
prompts. It is advisory: it colours a chip, it blocks nothing.

| Where | What |
|---|---|
| `train.py` | Trains the model and writes `threat_model.json` |
| `../pydantic-ai-agent/src/spe_agent/threat_model.json`, `threat.py` | The model and `POST /threat-score` |
| `../copilotkit-chat/app/threat-indicator.tsx`, `lib/threat*.ts` | The chip under the chat input, scored while typing |
| `../../report/threat_model.json`, `sperange_report.py` | The same model on the archived chats' user turns, in the runs browser |

## The model

The prompt's first 6000 characters are embedded with `BAAI/bge-m3` (1024 dimensions; on de.NBI
`vllm/BAAI/bge-m3`), the embedding is L2-normalised, and nine logistic regressions score it: one
general head and eight category heads. `threat_model.json` holds their weights, thresholds and
cross-validation numbers; scoring is a dot product, with no dependency.

| Head | In-domain examples | What it collects |
|---|---|---|
| general | 47 | every adversarial prompt |
| Prompt injection or jailbreak | 6, plus 4,075 public | injections, fabricated history, the public datasets' positives |
| Secrets and credentials | 10 | secret probes, "paste the output verbatim" |
| System prompt disclosure | 4 | |
| Data exfiltration | 4 | output downloads, patient rows |
| Network egress | 6 | external hosts, the metadata address |
| Registry and audit tampering | 9 | deceptive registrations, hidden ids, tampered results |
| Shell injection | 6 | |
| Destructive or overload | 2 | |

**The number.** Each head's probability is put on its own scale: 50 is the head's `elevated`
threshold, above which 5% of benign in-domain prompts score; 75 its `high` threshold, 1%. The chip
shows the general head; the details show every category. Levels: low under 50, elevated from 50,
high from 75.

**How good it is** (five-fold cross-validation over the in-domain prompts, near-duplicates kept in
one fold, public data always in training): general AUC 0.97; 91% of the adversarial prompts reach
elevated, 66% high. On the real participant prompts alone 17% of the benign ones reach elevated,
not 5%: the threshold is set mostly on generated benign prompts. Per category the AUC is 0.99 to
1.0 for secrets, egress and shell injection, 0.93 for registry tampering, 0.88 for injection, and
weak for data exfiltration (0.72), system prompt disclosure (0.58) and destructive or overload
(two examples). The interface marks heads with fewer than five examples or an AUC under 0.8.

**What it misses.** Violations that read like ordinary work (show the patient rows, clean up the
share, run everything three times): nothing in the embedding carries the runbook. It sees one
message, not a conversation. Prompts it was trained on score higher than new ones will.

## Retraining

```bash
python train.py data.jsonl emb_bge-m3.npy ../pydantic-ai-agent/src/spe_agent/threat_model.json
cp ../pydantic-ai-agent/src/spe_agent/threat_model.json ../../report/threat_model.json
```

Needs numpy and scikit-learn. `data.jsonl` has one prompt per line: `text`, `label` (1
adversarial), `source` (`spe`, `benign_synth`, or a public set's name) and, for `spe` rows,
`category` (the names in `CATEGORIES` in `train.py`, or `benign`). The embeddings file holds one
row per line of `data.jsonl`, from the same embedding model the agent will call. In-domain rows
weigh ten times a public row. `--eval-only` prints the cross-validation and writes nothing.

The training data is not in the repository: it holds what participants typed. The model of
2026-11-12 was trained on 12,264 public prompts (deepset/prompt-injections,
jackhhao/jailbreak-classification, xTRam1/safe-guard-prompt-injection), 100 hand-labelled user
turns from the archived runs (47 adversarial) and 297 generated benign bioinformatics requests.
