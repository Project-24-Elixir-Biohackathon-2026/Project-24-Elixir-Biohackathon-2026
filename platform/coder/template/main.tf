# Coder template: one workspace = one SPE evaluation instance.
# Spike: Terraform only wraps the existing Ansible playbooks (create.yml on
# start, destroy.yml on stop/delete) and runs them from the repo checkout on
# the controller. Presets come from testbeds/*.yml next to this file.
terraform {
  required_providers {
    coder = {
      source = "coder/coder"
    }
  }
}

variable "spe_ansible_dir" {
  type        = string
  description = "Path of platform/ansible in the repo checkout on the provisioner host"
  default     = "/home/ubuntu/ansible-wip/elixir-biohackathon-2026-test/platform/ansible"
}

variable "coder_agent_url" {
  type        = string
  description = "Coder URL as seen from inside the SPE VMs. Differs from the access URL while the portal is only reachable as localhost; empty = use the access URL."
  default     = "http://10.0.2.245:7080"
}

data "coder_provisioner" "me" {}
data "coder_workspace" "me" {}
data "coder_workspace_owner" "me" {}

# --- presets (git-driven) -----------------------------------------------------
locals {
  testbeds = {
    for f in fileset(path.module, "testbeds/*.yml") :
    trimsuffix(basename(f), ".yml") => yamldecode(file("${path.module}/${f}"))
  }
}

data "coder_workspace_preset" "testbed" {
  for_each    = local.testbeds
  name        = each.value.name
  description = try(each.value.description, null)
  default     = try(each.value.default, false)
  parameters = {
    for k, v in each.value.parameters : k => try(tostring(v), jsonencode(v))
  }
}

# --- parameters ---------------------------------------------------------------
data "coder_parameter" "samples" {
  name         = "samples"
  display_name = "GIAB samples"
  type         = "list(string)"
  form_type    = "multi-select"
  default      = jsonencode(["HG002", "HG003", "HG004", "HG005"])
  mutable      = true
  order        = 1
  dynamic "option" {
    for_each = ["HG002", "HG003", "HG004", "HG005"]
    content {
      name  = option.value
      value = option.value
    }
  }
}

data "coder_parameter" "tiers" {
  name         = "tiers"
  display_name = "Data tiers"
  description  = "Which data tiers are seeded and registered in DRS."
  type         = "list(string)"
  form_type    = "multi-select"
  default      = jsonencode(["ref", "genomes", "registry", "secret"])
  mutable      = true
  order        = 2
  dynamic "option" {
    for_each = ["ref", "genomes", "registry", "secret"]
    content {
      name  = option.value
      value = option.value
    }
  }
}

data "coder_parameter" "workflows" {
  name         = "workflows"
  display_name = "TRS workflows"
  type         = "list(string)"
  form_type    = "multi-select"
  default      = jsonencode(["wes-drs-smoke", "gatk-hc-chr20"])
  mutable      = true
  order        = 3
  dynamic "option" {
    for_each = ["wes-drs-smoke", "gatk-hc-chr20"]
    content {
      name  = option.value
      value = option.value
    }
  }
}

locals {
  canary_types = {
    registry_tokens    = "Registry tokens (surnames, study ids)"
    honeypot_files     = "Honeypot files"
    vcf_variants       = "Fake VCF variants"
    flag_file          = "Flag file"
    drs_metadata       = "DRS metadata"
    trs_descriptions   = "TRS descriptions"
    workflow_comments  = "Workflow comments"
    service_info       = "Service-info"
  }
}

data "coder_parameter" "canaries" {
  name         = "canaries"
  display_name = "Canary types"
  type         = "list(string)"
  form_type    = "multi-select"
  default      = jsonencode(keys(local.canary_types))
  mutable      = true
  order        = 4
  dynamic "option" {
    for_each = local.canary_types
    content {
      name  = option.value
      value = option.key
    }
  }
}

data "coder_parameter" "flavor" {
  name         = "flavor"
  display_name = "VM flavor"
  type         = "string"
  form_type    = "dropdown"
  default      = "de.NBI mini"
  mutable      = true
  order        = 5
  option {
    name  = "mini (4 vCPU / 8 GB)"
    value = "de.NBI mini"
  }
  option {
    name  = "small"
    value = "de.NBI small"
  }
}

data "coder_parameter" "seed" {
  name         = "seed"
  display_name = "Seed"
  description  = "Drives every synthetic value and canary. Leave 0 to derive one from the workspace id; set it to reproduce another instance exactly."
  type         = "number"
  default      = 0
  mutable      = true
  order        = 6
}

data "coder_parameter" "smoke_test" {
  name         = "smoke_test"
  display_name = "Run WES smoke test after creation"
  type         = "bool"
  form_type    = "switch"
  default      = true
  mutable      = true
  order        = 7
}

data "coder_parameter" "frontend" {
  name         = "frontend"
  display_name = "Chat frontend"
  description  = "openwebui: Open WebUI runs the agent loop (chats and the run report are archived on stop). agui: our own Pydantic AI agent with a CopilotKit chat (platform/agui; its chat sessions and run log are archived on stop)."
  type         = "string"
  form_type    = "radio"
  default      = "openwebui"
  mutable      = true
  order        = 8
  option {
    name  = "Open WebUI"
    value = "openwebui"
  }
  option {
    name  = "AG-UI agent (Pydantic AI + CopilotKit)"
    value = "agui"
  }
}

# --- derived values -----------------------------------------------------------
locals {
  instance = lower("cw-${data.coder_workspace_owner.me.name}-${data.coder_workspace.me.name}")
  seed     = data.coder_parameter.seed.value != "0" ? tonumber(data.coder_parameter.seed.value) : parseint(substr(sha256(data.coder_workspace.me.id), 0, 8), 16)
  canaries = jsondecode(data.coder_parameter.canaries.value)

  ansible_vars = merge(
    {
      spe_instance          = local.instance
      spe_seed              = local.seed
      spe_flavor            = data.coder_parameter.flavor.value
      spe_samples           = jsondecode(data.coder_parameter.samples.value)
      spe_tiers             = jsondecode(data.coder_parameter.tiers.value)
      spe_workflows         = jsondecode(data.coder_parameter.workflows.value)
      spe_run_smoke_test    = tobool(data.coder_parameter.smoke_test.value)
      spe_frontend          = data.coder_parameter.frontend.value
      spe_coder_owner       = data.coder_workspace_owner.me.name
      spe_coder_owner_email = data.coder_workspace_owner.me.email
      spe_coder_workspace   = data.coder_workspace.me.name
      spe_coder_agent_token = nonsensitive(coder_agent.main.token)
      spe_coder_init_script = local.agent_init_script
    },
    { for k, _ in local.canary_types : "spe_canary_${k}" => contains(local.canaries, k) },
  )

  agent_init_script = var.coder_agent_url == "" ? coder_agent.main.init_script : replace(
    coder_agent.main.init_script,
    trimsuffix(data.coder_workspace.me.access_url, "/"),
    trimsuffix(var.coder_agent_url, "/"),
  )
}

# --- agent + app --------------------------------------------------------------
resource "coder_agent" "main" {
  os   = "linux"
  arch = "amd64"

  display_apps {
    vscode          = false
    vscode_insiders = false
    web_terminal    = true
    ssh_helper      = true
    port_forwarding_helper = true
  }
}

# One app per frontend; only the selected one exists, so the dashboard shows a
# single button. Both are bound to 127.0.0.1 on the VM and reached through the
# agent (share = owner: only the workspace owner may open them).
resource "coder_app" "openwebui" {
  count        = data.coder_parameter.frontend.value == "openwebui" ? 1 : 0
  agent_id     = coder_agent.main.id
  slug         = "openwebui"
  display_name = "OpenWebUI"
  icon         = "/icon/openai.svg"
  url          = "http://localhost:8080"
  subdomain    = true
  share        = "owner"

  healthcheck {
    url       = "http://localhost:8080/health"
    interval  = 10
    threshold = 30
  }
}

resource "coder_app" "chat" {
  count        = data.coder_parameter.frontend.value == "agui" ? 1 : 0
  agent_id     = coder_agent.main.id
  slug         = "chat"
  display_name = "Chat (AG-UI)"
  icon         = "/icon/terminal.svg"
  url          = "http://localhost:3000"
  subdomain    = true
  share        = "owner"

  healthcheck {
    url       = "http://localhost:3000/"
    interval  = 10
    threshold = 30
  }
}

# --- the instance (Ansible) ----------------------------------------------------
# Exists only while the workspace is started: stop = destroy.yml, start =
# create.yml from the same seed, so a restart gives an identical fresh instance.
resource "terraform_data" "spe" {
  count = data.coder_workspace.me.start_count

  input = {
    instance    = local.instance
    ansible_dir = var.spe_ansible_dir
    vars_json   = jsonencode(local.ansible_vars)
  }

  provisioner "local-exec" {
    command = "${path.module}/run-ansible.sh create.yml"
    environment = {
      SPE_ANSIBLE_DIR = self.input.ansible_dir
      SPE_VARS_JSON   = self.input.vars_json
    }
  }

  provisioner "local-exec" {
    when    = destroy
    command = "${path.module}/run-ansible.sh destroy.yml"
    environment = {
      SPE_ANSIBLE_DIR = self.input.ansible_dir
      SPE_VARS_JSON   = self.input.vars_json
    }
  }
}

resource "coder_metadata" "spe" {
  count       = data.coder_workspace.me.start_count
  resource_id = terraform_data.spe[0].id

  item {
    key   = "instance"
    value = local.instance
  }
  item {
    key   = "seed"
    value = tostring(local.seed)
  }
  item {
    key   = "frontend"
    value = data.coder_parameter.frontend.value
  }
  item {
    key   = "runs archive"
    value = "/data-share/runs/<time>_${local.instance}/ (controller, written on stop/delete)"
  }
  item {
    key   = "canary record"
    value = "${var.spe_ansible_dir}/../output/${local.instance}/canaries.json (controller)"
  }
}
