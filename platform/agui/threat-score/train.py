"""Train the threat-score model the chat shows while typing: one general head and one head per category,
all logistic regressions on bge-m3 embeddings. Writes threat_model.json (weights, thresholds, CV numbers).

Usage: train.py data.jsonl emb_bge-m3.npy out.json [--eval-only]
"""
import json, re, sys, datetime, warnings
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
warnings.filterwarnings("ignore")

CATEGORIES = [  # id, label, the labels of data.jsonl it collects
    ("injection", "Prompt injection or jailbreak", ["public", "injection", "fabricated_history"]),
    ("secrets", "Secrets and credentials", ["secret_probe", "secret_echo"]),
    ("system_prompt", "System prompt disclosure", ["system_prompt"]),
    ("exfiltration", "Data exfiltration", ["output_exfiltration", "pii_exfiltration"]),
    ("egress", "Network egress", ["egress", "egress_metadata"]),
    ("registry", "Registry and audit tampering", ["deceptive_registration", "audit_evasion", "result_tampering", "provenance", "persistence"]),
    ("shell", "Shell injection", ["shell_injection"]),
    ("disruption", "Destructive or overload", ["destructive", "overload"]),
]
rows = [json.loads(l) for l in open(sys.argv[1])]
X = np.load(sys.argv[2]).astype(np.float64)
X /= np.linalg.norm(X, axis=1, keepdims=True)
y = np.array([r["label"] for r in rows]); src = np.array([r["source"] for r in rows])
cat = np.array([r["category"] if r["source"] == "spe" else ("public" if r["label"] else "benign") for r in rows])
texts = [r["text"] for r in rows]
dom = np.isin(src, ["spe", "benign_synth"]); spe = src == "spe"
groups = np.array([re.sub(r"[0-9a-f]{8,}", "X", t.lower()).replace(" ", "")[:120] for t in texts])

def head(Xtr, ytr, w=None):
    return LogisticRegression(C=1.0, max_iter=3000, class_weight="balanced").fit(Xtr, ytr, sample_weight=w)

def targets():
    out = {"general": y}
    for cid, _, members in CATEGORIES:
        out[cid] = np.isin(cat, members).astype(int)
    return out

T = targets()
# In-domain rows count 10x: 397 of them against 12,000 public ones would otherwise not move the heads.
W = np.where(dom, 10.0, 1.0)

# Out-of-fold scores for the in-domain prompts (SPE + synthetic benign), near-duplicates in one fold.
idx = np.where(dom)[0]; oof = {k: np.full(len(rows), np.nan) for k in T}
for tr_i, te_i in StratifiedGroupKFold(5, shuffle=True, random_state=0).split(idx, y[idx], groups[idx]):
    tr = ~dom; tr[idx[tr_i]] = True; te = idx[te_i]
    for k, t in T.items():
        if t[tr].sum() == 0: continue
        oof[k][te] = head(X[tr], t[tr], W[tr]).predict_proba(X[te])[:, 1]

def thresholds(scores_benign):
    """elevated: 5% of in-domain benign prompts score above it; high: 1%."""
    return {"elevated": round(float(np.quantile(scores_benign, 0.95)), 4), "high": round(float(np.quantile(scores_benign, 0.99)), 4)}

report = {}
benign_dom = dom & (y == 0)
for k, t in T.items():
    ok = dom & ~np.isnan(oof[k]); s = oof[k][ok]; tt = t[ok]
    thr = thresholds(oof[k][benign_dom & ok])
    pos = s[tt == 1]
    report[k] = {"examples": int(t[dom].sum()), "auc": round(float(roc_auc_score(tt, s)), 3) if 0 < tt.sum() < len(tt) else None,
                 "recall_elevated": round(float((pos >= thr["elevated"]).mean()), 2) if len(pos) else None,
                 "recall_high": round(float((pos >= thr["high"]).mean()), 2) if len(pos) else None, **thr}
    print("%-14s n=%3d auc=%s recall@elev=%s recall@high=%s thr=%s" % (k, report[k]["examples"], report[k]["auc"], report[k]["recall_elevated"], report[k]["recall_high"], thr))
# The general score on SPE prompts only (what the earlier report measured)
s = oof["general"][spe]; print("general, SPE only: auc=%.3f" % roc_auc_score(y[spe], s),
      "recall@elev=%.2f recall@high=%.2f fpr_spe@elev=%.2f" % ((s[y[spe] == 1] >= report["general"]["elevated"]).mean(), (s[y[spe] == 1] >= report["general"]["high"]).mean(), (s[y[spe] == 0] >= report["general"]["elevated"]).mean()))
if "--eval-only" in sys.argv: sys.exit()

def export(k):
    c = head(X, T[k], W)
    return {"weights": [round(float(v), 5) for v in c.coef_[0]], "bias": round(float(c.intercept_[0]), 5)}

labels = {"general": "Threat score", **{cid: label for cid, label, _ in CATEGORIES}}
model = {"version": 1, "trained": datetime.date.today().isoformat(), "embedding_model": "BAAI/bge-m3", "dimensions": int(X.shape[1]),
         "input": "the prompt's first 6000 characters, embedding L2-normalised; score = sigmoid(weights . x + bias)",
         "training": {"public": int((~dom).sum()), "in_domain": int(dom.sum()), "in_domain_adversarial": int((dom & (y == 1)).sum())},
         "heads": [{"id": k, "label": labels[k], **{f: report[k][f] for f in ("examples", "auc", "elevated", "high")}, **export(k)} for k in T]}
json.dump(model, open(sys.argv[3], "w"), separators=(",", ":"))
print("wrote", sys.argv[3])
