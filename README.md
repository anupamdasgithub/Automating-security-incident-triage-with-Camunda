# Agentic Variant — AI Agent Sub-process + MCP

> This branch re-architects the blueprint's tool dispatch onto Camunda's agentic
> orchestration. For the blueprint implementation itself, its stubs and its
> coverage against the original, see the README on `main`.

---

## Intent

The blueprint selects investigation tools by having a model emit a list of
strings, which Zeebe then matches against BPMN element IDs:

```xml
<zeebe:adHoc activeElementsCollection="=agent_plan.tools" />
```

Rename one element and the tool silently never runs. The model has to know the
process's internal identifiers, and there is no schema, no argument validation
and no discovery — the coupling is a side channel dressed as a contract.

This branch replaces that with MCP. Tools are published by a server with typed
input schemas, the agent discovers them at runtime and calls them by contract,
and Camunda's own agent loop drives the iteration. The BPMN no longer needs to
know which tools exist.

The decision logic downstream of the tools is **unchanged**. Nothing in
`Content Enrichment`, `Unified Incident Builder`, the ISO chain, the GDPR
gateway or the report sections was edited. That is deliberate: the point is to
show the dispatch mechanism can be replaced without disturbing the process the
blueprint actually describes.

---

## What changed

| Removed | Added |
|---|---|
| `AI_Investigation_Tools` ad-hoc subprocess and its three tool elements | `AI_Agent_Investigation` — AI Agent Sub-process (template v11) |
| `Gateway_05yofwt` "At least 1 tool selected?" | `MCP_SOC_Tools` — MCP Remote Client service task (template v3) |
| `agent_plan.tools` → element-ID dispatch | `Map_MCP_Tool_Results` — FEEL adapter |

New path:

```
Analyze Threat (AI)
  → AI Investigation Agent (MCP)
       └─ SOC Tools (MCP)
  → Map MCP Tool Results
  → Gateway_0f83elm → Content Enrichment → … (unchanged)
```

The three tools keep the blueprint's names so the correspondence stays legible:
`threat_intel_lookup`, `asset_lookup`, `check_gdpr_relevance`.

---

## The adapter

MCP returns tool results in its own shape. Rather than edit ~40 downstream FEEL
expressions, `Map_MCP_Tool_Results` normalises the results onto the variable
contract the blueprint already expects.

Each result is located by tool name and parsed out of the MCP text block:

```
from json(
  toolCallResults[content.name = "<tool>"][1].content.content[1].text
)
```

Note `content.name`, not `name` — the outer `name` is the BPMN element ID
(`MCP_SOC_Tools`), not the tool.

Three normalisations:

| Variable | Normalisation |
|---|---|
| `threat_intel` | flat MCP result wrapped in a `body` envelope, because downstream reads `threat_intel.body.{ports,hostnames,tags,cpes}` |
| `asset_result` | `hostname`→`asset_name`, `asset_class`→`asset_type`, `owner_unit`→`asset_owner`, `business_criticality`→`asset_criticality` |
| `gdpr_raw` | rebuilt as a Bedrock-shaped envelope whose `body.content[1].text` carries `RELEVANZ` / `KATEGORIE` / `RISIKO-ASSESSMENT` / `ACTION`, which twelve existing expressions parse |

`gdpr_result` and `mcp_tool_results_raw` are also emitted — the clean object and
the untouched tool output, for inspection.

---

## The model is fixtured, the orchestration is not

`MCP/llm_stub_server.py` serves an OpenAI-compatible `/v1/chat/completions`
endpoint. The AI Agent connector is pointed at it via **Provider: OpenAI
Compatible**, so every mechanism around the model runs for real — tool
discovery, dispatch, the feedback loop, result correlation, iteration limits.
Only the *choosing* is fixtured.

This is the same discipline as the Bedrock stub on `main`, one layer up. There,
the stub fakes a decision the blueprint then obeys. Here, Camunda's genuine
agent loop executes around a fixtured model output.

Two consequences worth stating plainly:

- **Runs cost nothing.** No API key, no provider account.
- **Runs are deterministic.** The same event produces the same tool calls every
  time, which makes the orchestration legible in a demo rather than confounded
  by model variance.

The stub reads the `tools` array on each request and calls back whatever it was
offered, matching on suffix. That matters because the agent namespaces
discovered tools by element ID — `MCP_MCP_SOC_Tools___threat_intel_lookup` —
a convention the stub never needs to hard-code.

Swapping in a live provider is two fields in the properties panel (Provider,
API key) with no BPMN change.

---

## Tools

`MCP/soc_mcp_server.py` publishes three tools over MCP Streamable HTTP:

| Tool | Behaviour |
|---|---|
| `threat_intel_lookup` | **real** — `internetdb.shodan.io`, free, no API key |
| `asset_lookup` | fixture — synthetic `TEST-*` inventory |
| `check_gdpr_relevance` | deterministic verdict from keyword indicators |

The Shodan call needs an explicit `User-Agent`; the default `Python-urllib/3.x`
is answered with 403 while the identical request from curl succeeds. 403, 404
and 429 are all treated as "no usable record" rather than faults, since RFC 5737
documentation ranges are never scanned.

---

## Running it

```bash
pip3 install "mcp>=1.28,<2" flask kafka-python --break-system-packages
./Scripts/start_stubs.sh
```

The `mcp<2` pin is required — SDK 2.0 renamed `FastMCP` to `MCPServer` with no
alias, and `pip install mcp` now resolves to 2.x.

Four servers must be listening before a run:

| Port | Server |
|---|---|
| 9995 | LLM stub (OpenAI-compatible) |
| 9996 | MCP server |
| 9997 | Bedrock stub (blueprint's six AI calls) |
| 9998 | Child scenario stub |

Then publish an event:

```bash
python3 Scripts/incident_producer.py ISO_THREAT
```

`ISO_THREAT` is the useful scenario: its topic carries a routable IP, so
`threat_intel_lookup` returns live scan data rather than a documentation-range
miss.

---

## Both parents receive every event

The blueprint on `main` and this variant both declare a Kafka message start
event on `security-events`. They use **different consumer groups**:

| Process | groupId |
|---|---|
| `Process_vprqirj` (blueprint) | `incident-intake-consumer` |
| `Process_agentic_soc` (agentic) | `incident-intake-consumer-agentic` |

Kafka delivers each message once per consumer group. A shared group would have
distributed partitions between the two, so a published event would start *one*
of them non-deterministically. Separate groups mean both receive every event —
one producer run triggers both variants, which is what makes the side-by-side
comparison possible.

Consequence: one event produces two parent instances and two child instances,
and two tasks appear in Tasklist. That is by design, not duplication.

```bash
docker exec kafka kafka-consumer-groups.sh --bootstrap-server localhost:9094 \
  --describe --group incident-intake-consumer-agentic
```

---

## Verified

One `ISO_THREAT` event, zero cost:

```
2 model calls, 3 parallel tool calls, clean loop termination
threat_intel_lookup -> 172.67.182.45
  ports [80,443,2052,2082,2083,2086,2087,8080,8443,8880], tags [cdn],
  cpes [cpe:/a:cloudflare:cloudflare]

incident_object:
  threat_score            12
  threat_ports_string     80, 443, 2052, ...
  threat_services_string  cloudflare:cloudflare
  asset_criticality       high
  asset_name              TEST-DB-02
  risk_level              HIGH
  action                  investigate
```

`threat_score = 12` is the blueprint's own formula — ten ports plus one tag
scored double — computed from live scan data reaching unmodified FEEL.

---

## Known gaps

**The agent runs after `Prepare Incident Context`.** That subprocess builds
`pre_incident_object` before any tool has executed, so it still carries
`Unknown` values. `Unified_Incident_Builder` runs later and recomputes them
correctly, so nothing downstream is wrong — but the intermediate object is
misleading. Moving the agent ahead of it, replacing the planner REST task
outright, is the clean fix.

**`Gateway_0f83elm` is vestigial.** It was the merge point for the two branches
of the gateway this variant removed. It now has one incoming and one outgoing
flow and can be deleted.

**The child still prompts for `scenario_type`.** The Kafka event carries it, but
the intake form asks anyway — an artifact of the blueprint's manual design.

**Language mismatch in the blueprint's own matching.** `sim_input.incident_topic`
is English, while several FEEL branches match German substrings
(`datenabfluss`, `kundendaten`, `personenbezogene daten`). Language-neutral
terms (`proxy`, `vpn`, `scan`) still match, which is why PROXY classification
works. The rule-based GDPR branch does not fire on English topics; GDPR
relevance currently comes entirely from the MCP tool via `gdpr_raw`. This is
pre-existing and not introduced by this branch.

**MCP Remote Client opens a connection per activation.** `clientCache` is false,
so each discovery and each tool call creates and closes its own HTTP client —
four sessions in two seconds on a typical run. Camunda documents the Remote
Client as intended for prototyping; the MCP Client connector, registered in
runtime config with persistent connections, is the production path.
