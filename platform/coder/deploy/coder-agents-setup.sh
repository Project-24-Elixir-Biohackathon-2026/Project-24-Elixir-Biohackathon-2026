#!/usr/bin/env bash
# Configure Coder Agents (the portal's built-in chat agent) to use an
# OpenAI-compatible LLM endpoint: one provider and one or more models per run;
# run it once per endpoint. Idempotent: an existing provider of the same name is
# reused (its base URL and key are updated), existing models are left alone.
# The portal has two endpoints (keys in /etc/sperange/coder.env): the defaults
# below set up de.NBI's litellm with gemma; the second run sets up the BI de.NBI
# vLLM endpoint with Qwen3-Coder-Next, the portal's default model since 2026-11-04:
#
#   SPE_LLM_PROVIDER=bi-denbi SPE_LLM_PROVIDER_LABEL="BI de.NBI vLLM" \
#   SPE_LLM_BASE_URL=$(sudo grep '^BI_DENBI_LLM_BASE_URL=' /etc/sperange/coder.env | cut -d= -f2-) \
#   SPE_LLM_API_KEY=$(sudo grep '^BI_DENBI_LLM_API_KEY=' /etc/sperange/coder.env | cut -d= -f2-) \
#   SPE_LLM_MODELS="vllm/Qwen/Qwen3-Coder-Next:65536:Qwen3 Coder Next (BI de.NBI):8192" \
#   platform/coder/deploy/coder-agents-setup.sh
#
# That endpoint serves the model with a 64k window and Coder asks for 32k output
# tokens unless capped, so the model needs context_limit 65536 and
# max_output_tokens 8192 (the fourth field) or a long chat fails once its history
# passes 33k tokens. The model ids there carry the "vllm/" prefix.
#
# Environment (defaults read the portal's own config files):
#   CODER_URL             Coder API, default http://127.0.0.1:7080
#   CODER_SESSION_TOKEN   an owner's token; default: CODER_SESSION_TOKEN in /etc/sperange/sync.env
#   SPE_LLM_API_KEY       the endpoint's key; default: DENBI_LLM_API_KEY in /etc/sperange/coder.env
#   SPE_LLM_BASE_URL      default https://denbi-llm-api-internal.bihealth.org/v1
#   SPE_LLM_PROVIDER      provider name (lowercase), default denbi
#   SPE_LLM_PROVIDER_LABEL display name, default "de.NBI LLM"
#   SPE_LLM_MODELS        comma-separated "model[:context_limit[:display name[:max_output_tokens]]]",
#                         default "gemma-4-31b:131072:Gemma 4 31B (de.NBI)";
#                         the first one created becomes the organization's default model.
#                         Not qwen3.8-27b or mistral-medium-3.5: their chat
#                         templates reject a system message that is not the
#                         first message, and Coder Agents sends one mid-conversation
#                         (gpt-oss-120b, gemma-4-31b and glm-5.3 accept it; probed 2026-11-02).
#   SPE_CODER_ORG         organization, default "default"
#
# Undo: delete the models, then the provider (both endpoints accept DELETE).
set -euo pipefail

CODER_URL=${CODER_URL:-http://127.0.0.1:7080}
CODER_SESSION_TOKEN=${CODER_SESSION_TOKEN:-$(sudo grep '^CODER_SESSION_TOKEN=' /etc/sperange/sync.env | cut -d= -f2-)}
SPE_LLM_API_KEY=${SPE_LLM_API_KEY:-$(sudo grep '^DENBI_LLM_API_KEY=' /etc/sperange/coder.env | cut -d= -f2-)}
SPE_LLM_BASE_URL=${SPE_LLM_BASE_URL:-https://denbi-llm-api-internal.bihealth.org/v1}
SPE_LLM_PROVIDER=${SPE_LLM_PROVIDER:-denbi}
SPE_LLM_PROVIDER_LABEL=${SPE_LLM_PROVIDER_LABEL:-de.NBI LLM}
SPE_LLM_MODELS=${SPE_LLM_MODELS:-gemma-4-31b:131072:Gemma 4 31B (de.NBI)}
SPE_CORG=${SPE_CODER_ORG:-default}
B="$CODER_URL/api/v2"
H=(-H "Coder-Session-Token: $CODER_SESSION_TOKEN" -H 'Content-Type: application/json')

api() { curl -sS --fail-with-body "${H[@]}" "$@"; }
json() { python3 -c "import json,sys; print(json.dumps($1))" "${@:2}"; }

# Provider: find by name, else create. The type "openai-compat" is what the
# server accepts for "OpenAI-compatible" (Coder 2.38). The key travels as a
# list: a bare string on create, {"api_key": ...} on update (as the dashboard
# sends it).
pid=$(api "$B/ai/providers" | python3 -c '
import json, sys
name = sys.argv[1]
print(next((p["id"] for p in json.load(sys.stdin) if p["name"] == name), ""))' "$SPE_LLM_PROVIDER")
if [[ -z $pid ]]; then
  body=$(json '{"type": "openai-compat", "name": sys.argv[1], "display_name": sys.argv[2],
                "base_url": sys.argv[3], "api_keys": [sys.argv[4]], "enabled": True}' \
         "$SPE_LLM_PROVIDER" "$SPE_LLM_PROVIDER_LABEL" "$SPE_LLM_BASE_URL" "$SPE_LLM_API_KEY")
  pid=$(api -X POST -d "$body" "$B/ai/providers" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
  echo "provider $SPE_LLM_PROVIDER created ($pid)"
else
  body=$(json '{"display_name": sys.argv[1], "base_url": sys.argv[2],
                "api_keys": [{"api_key": sys.argv[3]}], "enabled": True}' \
         "$SPE_LLM_PROVIDER_LABEL" "$SPE_LLM_BASE_URL" "$SPE_LLM_API_KEY")
  api -X PATCH -d "$body" "$B/ai/providers/$pid" >/dev/null
  echo "provider $SPE_LLM_PROVIDER updated ($pid)"
fi

# Models: create the ones that do not exist yet for this provider.
existing=$(api "$B/organizations/$SPE_CORG/chats/models" | python3 -c '
import json, sys
pid = sys.argv[1]
print(" ".join(m["model"] for m in json.load(sys.stdin)["models"] if m["ai_provider_id"] == pid))' "$pid")
first=true
IFS=, read -ra specs <<<"$SPE_LLM_MODELS"
for spec in "${specs[@]}"; do
  IFS=: read -r model limit label maxout <<<"$spec"
  model=${model# }
  if [[ " $existing " == *" $model "* ]]; then
    echo "model $model exists, left as is"
  else
    body=$(json '{"ai_provider_id": sys.argv[1], "model": sys.argv[2], "enabled": True,
                  "is_default": sys.argv[3] == "true",
                  **({"context_limit": int(sys.argv[4])} if sys.argv[4] else {}),
                  **({"display_name": sys.argv[5]} if sys.argv[5] else {}),
                  **({"model_config": {"max_output_tokens": int(sys.argv[6])}} if sys.argv[6] else {})}' \
           "$pid" "$model" "$first" "${limit:-}" "${label:-}" "${maxout:-}")
    api -X POST -d "$body" "$B/organizations/$SPE_CORG/chats/models" >/dev/null
    echo "model $model created$([[ $first == true ]] && echo ' (default)')"
  fi
  first=false
done

echo "== state"
api "$B/organizations/$SPE_CORG/chats/models" | python3 -c '
import json, sys
d = json.load(sys.stdin)
for p in d["providers"]:
    print(" provider:", p.get("display_name"), p["type"], "enabled" if p.get("enabled") else "disabled",
          "key set" if p.get("has_effective_api_key") else "NO KEY", "available" if p.get("available") else "NOT AVAILABLE")
for m in d["models"]:
    print(" model:", m["model"], m.get("display_name") or "", "default" if m.get("is_default") else "",
          "enabled" if m.get("enabled") else "disabled", m.get("context_limit"))
if d.get("unsupported_providers"):
    print(" unsupported providers:", d["unsupported_providers"])'
