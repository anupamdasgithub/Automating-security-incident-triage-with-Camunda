# Intelligent Security Incident Processing — Camunda 8.10 Self-Managed

> AI-driven incident triage for Security Operations Centers — running end-to-end on a local Camunda 8.10 stack, at no cost, with a human always in the loop.

*A working local implementation of the Camunda blueprint: <https://marketplace.camunda.com/en-US/apps/830621/intelligent-security-incident-processing>*

---

## Executive Summary

This repository is a **running implementation** of the Intelligent Security Incident Processing blueprint on Camunda 8.10 Self-Managed (Docker Compose).

The blueprint calls AWS Bedrock for every AI step, which requires live credentials and bills per run. Here those six calls are served by a local stub that reproduces the exact Bedrock response envelope — so the decision logic, the FEEL expressions and the process structure remain the blueprint's own, unmodified.

The result is a complete, reproducible run: from scenario intake through AI planning, dynamic investigation tools, analyst validation and the final audit report — with no AWS account and no per-run cost.

<p align="center">
  <img src="Images/Local_Run_Coverage.png" alt="What this local run covers against the blueprint feature areas" width="800">
</p>

---

## Overview

The implementation preserves the blueprint's separation of responsibilities and adds a local execution layer beneath it.

| Layer | Responsibility |
|---|---|
| **Ingest & Normalization** | Data preparation — child process builds `incident_topic` and `raw_alert` |
| **Topic & Context** | Business interpretation — scenario type drives the investigation path |
| **AI Incident Planner** | Decision logic — selects which investigation tools run |
| **Local Stub Layer** | Serves the six AI calls in the Bedrock response shape (added here) |

---

## Contents

| Path | Purpose |
|---|---|
| `Blueprint/AI_Incident_Investigation.bpmn` | Parent process — planner, investigation tools, ISMS/ISO steps, report |
| `Blueprint/Incident_Intake_Selection.bpmn` | Child process — analyst scenario selection, incident topic + alert |
| `Blueprint/Incident_Type_Selection.form` | Tasklist form — scenario selection |
| `Blueprint/Incident_Validation.form` | Tasklist form — analyst validation |
| `Blueprint/Incident_Report.form` | Tasklist form — incident report |
| `bedrock_to_rest__stub_server.py` | Stand-in for the 6 AWS Bedrock AI calls (port 9997) |
| `incident_stub_server.py` | Stand-in for the child's scenario generator (port 9998) |
| `incident_producer.py` | Kafka producer — publishes synthetic security events to a topic |
| `REST_Outbound_Connector.json` | REST connector element template |
| `AWS_Bedrock_Outbound_Connector.json` | Bedrock connector element template (reference) |
| `Images/` | Diagrams and coverage charts |
| `LICENSE/` | MIT license and blueprint attribution |

---

## Process Overview

### 1. Scenario Setup *(Test Environment Only)*
The child process `Incident_Intake_Selection` initialises input data for demonstration and testing.

### 2. Incident Scenario Selection *(Test Environment Only)*
An analyst selects one of eight predefined scenarios in Tasklist. The script task maps that choice deterministically to an `incident_topic`; the REST task then retrieves the matching synthetic alert from the local stub.

### 3. AI Incident Analysis & Decision Engine
The `AI INCIDENT PLANNER` task:
- Processes the structured security event
- Selects the required investigation tools
- Prepares the subsequent investigation workflow

Its response is parsed into `agent_plan.tools`, which drives the ad-hoc subprocess.

### 4. AI Investigation Tools *(Dynamic)*
Activated by name from `agent_plan.tools`:
- Threat Intelligence Lookup — **real** Shodan call
- Asset Infrastructure Lookup
- GDPR Relevance Assessment

### 5. Security Incident Validation *(Human-in-the-Loop)*
A SOC analyst validates the automated assessment:
- Confirms final impact and priority
- Verifies the technical assessment
- Optionally adds analyst comments

### 6. Security Incident Report
Automatically generated, containing:
- Incident summary
- Technical analysis
- Compliance assessment (e.g. GDPR)
- Recommended response actions

---

## Core Architectural Principles

1. **Structured data instead of raw logs** — the AI Incident Planner processes only structured event data (JSON), never uncontrolled raw logs.
2. **Deterministic topic generation** — every scenario type maps to a unique incident topic via predefined rules.
3. **Clear separation of responsibilities** — Ingest (technical prep), Topic Engine (business classification), Planner (decision making).
4. **Human-in-the-loop validation** — a SOC analyst reviews every automated decision to minimize false classifications.
5. **Auditability** — every decision is transparent, documented, traceable, and fully auditable.
6. **Unmodified decision logic** — the stubs change *where* the AI responses come from, never *how* they are interpreted. No downstream FEEL expression was altered.

---

## AI Incident Planner

The central decision engine of the platform. It:
- Analyzes the incident context
- Determines the required investigation activities
- Selects the appropriate investigation tools

All outputs are generated as strictly structured JSON, ensuring deterministic downstream processing.

In this implementation the planner is served by `bedrock_to_rest__stub_server.py`. Despite standing in for Bedrock, it **does not implement the Bedrock protocol** — it is a plain REST endpoint reproducing the response envelope the blueprint's FEEL expects:

```
{ "body": { "content": [ {...}, { "text": "```json{...}```" } ] } }
```

Each task reads `body.content[1].text`, strips the ```` ```json ```` fences and parses it. Because the stub returns that exact shape, the planner's parsing, the `agent_plan` construction and the tool dispatch all remain the blueprint's own.

Fixture data is synthetic throughout: RFC 5737 documentation IPs (`198.51.100.x`, `192.0.2.x`) and `TEST-*` hostnames.

---

## Supported Investigation Tools

**Threat Intelligence Lookup**
Checks IP addresses and external indicators against known threat intelligence sources. **Called for real** against `internetdb.shodan.io` (free, no API key).

**Asset Infrastructure Lookup**
Identifies internal systems, evaluates their business criticality, and determines responsible organizational units.

**GDPR Relevance Assessment**
Determines whether an incident involves personal data and whether GDPR obligations may apply.

---

## What Is Stubbed and What Is Real

All nine REST activities use the Camunda REST outbound connector
(`io.camunda:http-json:1`, template `io.camunda.connectors.HttpJson.v2` v13).
Only the target URL differs:

| Task | Target |
|---|---|
| AI Incident Planner | stub `:9997/planner` |
| check_gdpr_relevance | stub `:9997/gdpr` |
| write_iso_report | stub `:9997/iso` |
| Threat Interpretation AI | stub `:9997/threat` |
| Short_Description AI | stub `:9997/short_desc` |
| llm_explanation AI | stub `:9997/explanation` |
| Threat Intelligence Lookup | **real** — `internetdb.shodan.io` (free, no API key) |
| Prepare ISO Ticket | **real** — `httpbin.org/post` (the blueprint's own placeholder) |
| Prepare GDPR Ticket | **real** — `httpbin.org/post` (the blueprint's own placeholder) |

---

## Integration with Operational Systems

The blueprint states that validated security incidents can be forwarded to downstream platforms such as ServiceNow.

In the BPMN, **Ticket Creation is an embedded subprocess** whose two REST tasks post to `httpbin.org` and then hardcode the result: `ticket_id: "INC-SIM-10203"`, `status: "SIMULATED"`, `platform: "ITSM Platform"`. The ticket values never come from the response — the HTTP call is cosmetic. There is no ServiceNow connector, URL or credential anywhere.

Treat it as a placeholder. A real integration has to be built.

---

## How It Works — Walkthrough

A guided read of the mechanics, with the exact file locations so each claim can be checked in Modeler or in the XML.

### Where does `body.content[1].text` come from?

It is the **AWS Bedrock `invokeModel` response format**, not something the blueprint invented:

```json
{ "body": { "content": [ {...}, { "type": "text", "text": "...the model's answer..." } ] } }
```

`content` is an array of content blocks. The blueprint reads index **[1]** because that is where the text landed in its Bedrock responses. `bedrock_to_rest__stub_server.py` copies that indexing exactly — index 0 is an empty placeholder, index 1 carries the payload:

```python
def envelope(t):
    return {"body": {"content": [{"type":"text","text":""},
                                 {"type":"text","text":t}]}}
```

### What is the fence-strip pattern?

Language models habitually wrap JSON in markdown code fences:

````
```json
{"tools": [...]}
```
````

That is a *string*, not parseable JSON. So the FEEL strips the fences before parsing:

```
from json(
  trim(
    replace(
      replace(body.content[1].text, "```json", ""),
      "```", ""
    )
  )
)
```

The stub reproduces the fences so the strip has something to strip:

```python
def fenced(o):
    return "```json\n" + json.dumps(o, ensure_ascii=False) + "\n```"
```

### Where is the planner's result expression?

`AI_Incident_Investigation.bpmn`, **line 26**, task id `Activity_1rkk3bi`.
In Modeler: select **AI INCIDENT PLANNER → Output mapping → Result expression**.

It produces four fields: `raw`, `clean_json`, `agent_plan` and `tools`. `agent_plan` is built here — not later by the Agent Plan Normalizer.

### How does the gateway decide?

`AI_Incident_Investigation.bpmn`, **line 97**, sequence flow `Flow_03n63ai`, labelled **Ja**:

```
=agent_plan != null
and agent_plan.tools != null
and count(agent_plan.tools) > 0
```

In Modeler: click the arrow leaving *At least 1 tool selected?* → **Condition**.

### How does the ad-hoc subprocess pick its tools?

`AI_Incident_Investigation.bpmn`, **line 27**:

```xml
<bpmn:adHocSubProcess id="AI_Investigation_Tools" name="AI Investigation Tools">
  <bpmn:extensionElements>
    <zeebe:adHoc activeElementsCollection="=agent_plan.tools" />
```

In Modeler: click the **AI Investigation Tools** border (not a task inside) → **Active elements collection**.

**Matching is by element ID, not by name.** The three elements inside are:

| Element | id | name |
|---|---|---|
| serviceTask | `threat_intel_lookup` | Threat Intelligence Lookup |
| scriptTask | `asset_lookup` | Asset Infrastructure Lookup |
| serviceTask | `check_gdpr_relevance` | check_gdpr_relevance |

Zeebe compares each string in `agent_plan.tools` against those IDs. This is why the stub's fixture must be exactly:

```python
P = {"tools": ["threat_intel_lookup", "asset_lookup", "check_gdpr_relevance"], ...}
```

Rename one value and that tool silently never runs.

### Is the ad-hoc subprocess an AI feature?

No. `<bpmn:adHocSubProcess>` is **standard BPMN 2.0** — "these activities may run, in any order, some or none." Zeebe adds one attribute, `zeebe:adHoc activeElementsCollection`, to choose which ones at runtime.

Nothing here is AI-specific. The blueprint simply names it *AI Investigation Tools* and feeds it a list a model produced. Camunda does ship dedicated AI Agent connectors (`io.camunda.agenticai:aiagent:1`, `adhoctoolsschema:1`), but **this blueprint does not use them** — it is plain BPMN plus a REST call.

### Where is `sim_input` built?

In `Incident_Intake_Selection.bpmn`, across two tasks:

- **Line 45** — script task *Incident Type*, `resultVariable="sim_topic"` (derives `incident_topic` from `scenario_type`)
- **Line 7** — REST task, result expression assembles the final object:

```
={
  sim_input: {
    incident_topic: sim_topic.incident_topic,
    raw_alert: response.body.raw_alert,
    incident_type: response.body.incident_type
  }
}
```

The script's output was renamed from `sim_input` to `sim_topic`: with both the script and the REST task writing the same variable, `sim_input` came out `null`.

### How does the stub handle the `{"q":"go"}` body?

It ignores it. The routes never read the request:

```python
@app.route("/planner", methods=M)
def p(): return jsonify(envelope(fenced(P))), 200
```

The body exists only because the REST connector needs a **non-empty body** together with the `Content-Type: application/json` header — that combination is what avoids the `Content-Length header already present` error described below.

> All of these property panels stay collapsed in Modeler until `REST_Outbound_Connector.json` is **published** as an element template in the project.

## Implementation Notes

### REST connector needs an explicit `Content-Type` header

The AI tasks failed with:

```
ConnectorException: An error with the HTTP protocol occurred (500)
Caused by: ProtocolException: Content-Length header already present
```

Sending `headers = { "Content-Type": "application/json" }` on the task fixes it — the same pattern the blueprint's own REST tasks use. Without it, the Apache client and the connector both set `Content-Length` and the request is rejected before it leaves the runtime. Method and body shape were not the cause.

### Language

The blueprint ships with German strings in its FEEL expressions and Camunda Forms. Both BPMN files and all three forms have been translated to English; process IDs, variable names and connector bindings are unchanged.

---

## Vision

This implementation enables:
- A complete blueprint run without an AWS account or per-run cost
- Reproducible, deterministic incident assessments from fixed synthetic fixtures
- A clear boundary between what the blueprint decides and what an external model supplies
- Fully auditable documentation aligned with ISO 27001 and GDPR

## Environment

- Camunda 8.10-SNAPSHOT Self-Managed, Docker Compose (full profile)
- `camunda/connectors-bundle:8.10-SNAPSHOT`

---

## Secrets

None are committed. `connector-secrets.txt` and `.env` are git-ignored. Fill them locally from your own rotated credentials.

---

## License

MIT — see `LICENSE/`.

The original Camunda blueprint, its BPMN models and forms remain the property of
their respective authors under their own terms. The MIT license covers the
additions made here: the stub servers, the Kafka producer, the English
translations, the connector re-pointing and the documentation.

---

## Guiding Principle

**Structured data leads to clear decisions.**
**Clear decisions lead to secure processes.**
