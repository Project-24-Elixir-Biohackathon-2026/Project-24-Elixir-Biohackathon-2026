"""Compare every AG-UI session as the chat showed it before destroy.yml with the final archive
(docs/knowledge/agui-coder-e2e-check.md, *The final archive*). Usage: python3 agui-archive-compare.py <snapshot dir> <run>/agui
The snapshot dir holds sessions.json, api/<id>.json and journals/<id>.jsonl."""
import json, sys, glob, filecmp
S, R = sys.argv[1], sys.argv[2]
sessions = json.load(open(f"{S}/sessions.json"))
arch = {}
for f in glob.glob(f"{R}/chats/*.json"):
    d = json.load(open(f)); arch[d["id"]] = d


def text(c):
    # Message.content may be a string or a list of parts, as export.ts's textOf reads it
    if isinstance(c, list):
        c = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c)
    return (c or "").strip()


def in_order(want, have):
    # the wanted texts appear in the archived ones as an ordered subsequence, each matched exactly
    it = iter(have)
    return all(any(t == h for h in it) for t in want)


bad = int(set(arch) != {s["id"] for s in sessions})
for s in sessions:
    sid = s["id"]
    api = json.load(open(f"{S}/api/{sid}.json"))
    j_same = filecmp.cmp(f"{S}/journals/{sid}.jsonl", f"{R}/agui-journals/{sid}.jsonl", shallow=False)
    runs = sum(1 for l in open(f"{R}/agui-journals/{sid}.jsonl") if '"run_end"' in l)
    a = arch.get(sid)
    am = a["chat"]["messages"] if a else []
    au = [text(m.get("content")) for m in api["messages"] if m["role"] == "user"]
    xu = [text(m.get("content")) for m in am if m["role"] == "user"]
    aa = [t for t in (text(m.get("content")) for m in api["messages"] if m["role"] == "assistant") if t]
    # each archived assistant message's texts, in order: the message parts of its output (a compaction's summary
    # is one, its content being empty), or its content when it has none (content joins those parts)
    xa = [t for m in am if m["role"] == "assistant"
          for t in ([text(o.get("content")) for o in m.get("output") or [] if o.get("type") == "message"]
                    or [text(m.get("content"))]) if t]
    title_ok = a is not None and (s["title"] is None or a["title"] == s["title"])
    ok = j_same and a is not None and au == xu and in_order(aa, xa) and set(xa) <= set(aa) and title_ok
    bad += not ok
    print(f"{'OK ' if ok else 'BAD'} {sid[:8]} runs={runs} journal_identical={j_same} users api/arch={len(au)}/{len(xu)} "
          f"assistant texts api/arch={len(aa)}/{len(xa)} title_ok={title_ok}")
print("archived sessions:", len(arch), "listed:", len(sessions), "mismatches:", bad)
