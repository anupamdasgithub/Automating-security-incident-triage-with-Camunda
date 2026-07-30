# Intelligent Security Incident Processing — Camunda 8.10 Self-Managed

A working local run of the Camunda **Intelligent Security Incident Processing**
blueprint on Camunda 8.10 Self-Managed (Docker Compose), with the AWS Bedrock AI
calls replaced by local stubs so the process runs end-to-end at no cost.

Blueprint: <https://marketplace.camunda.com/en-US/apps/830621/intelligent-security-incident-processing>

---

## Contents

| File | Purpose |
|---|---|
| `AI_Incident_Investigation.bpmn` | Parent process — planner, investigation tools, ISMS/ISO steps, report |
| `Incident_Intake_Selection.bpmn` | Child process — analyst scenario selection, incident topic + alert |
| `Incident_Type_Selection.form` | Tasklist form — scenario selection |
| `Incident_Validation.form` | Tasklist form — analyst validation |
| `Incident_Report.form` | Tasklist form — incident report |
| `bedrock_stub_server.py` | Stand-in for the 6 AWS Bedrock AI calls (port 9997) |
| `incident_stub_server.py` | Stand-in for the child's scenario generator (port 9998) |
| `incident_producer.py` | Kafka producer — synthetic event source for the planned event-driven start |
| `REST_Outbound_Connector.json` | REST connector element template |
| `AWS_Bedrock_Outbound_Connector.json` | Bedrock connector element template (reference) |

---

## Why the stubs

The blueprint calls **AWS Bedrock** for every AI step — that needs live AWS
credentials and bills per run.

The stubs return the *same response envelope* Bedrock produces
(`body.content[1].text` holding fence-wrapped JSON), so **no downstream FEEL
expression was changed**. The decision logic is the blueprint's own.

Fixture data is synthetic throughout: RFC 5737 documentation IPs
(`198.51.100.x`, `192.0.2.x`) and `TEST-*` hostnames.

---

## Running

**1. Stack** (from your Camunda 8.10 compose directory — both files are
required; the base alone starts connectors without secrets):

```bash
docker compose -f docker-compose-full.yaml -f docker-compose.secrets.yaml up -d
```

**2. Stubs**

```bash
python3 incident_stub_server.py    # :9998
python3 bedrock_stub_server.py     # :9997
```

Verify from inside the connectors container — that is the path the REST
connector actually uses:

```bash
docker exec connectors wget -qO- http://host.docker.internal:9998/health
docker exec connectors wget -qO- http://host.docker.internal:9997/health
```

**3. Deploy** both BPMN files and the forms via Web Modeler.

**4. Run** from **Tasklist → Processes → AI Incident Investigation Blueprint → Start**,
then complete the **ISMS Scenario Type Selection** task.

> Avoid Modeler's app-level *Deploy & run* — it starts every executable process
> in the process application, so the child spawns a second standalone instance
> next to the one the parent calls. Tasklist starts the parent only, and is the
> correct end-user entry point.

---

## Notes

### REST connector needs an explicit `Content-Type` header

The AI tasks failed with:

```
ConnectorException: An error with the HTTP protocol occurred (500)
Caused by: ProtocolException: Content-Length header already present
```

Sending `headers = { "Content-Type": "application/json" }` on the task fixes it
— the same pattern the blueprint's own REST tasks use. Without it, the Apache
client and the connector both set `Content-Length` and the request is rejected
before it leaves the runtime. Method and body shape were not the cause.

### Ticket creation is simulated

The blueprint states incidents *can be* forwarded to systems such as ServiceNow.
In the BPMN, **Ticket Creation is a subprocess** — there is no ServiceNow
connector, URL or credential. It is a placeholder; a real integration has to be
built.

### Kafka-triggered start — planned



---

## Environment

- Camunda 8.10-SNAPSHOT Self-Managed, Docker Compose (full profile)
- `camunda/connectors-bundle:8.10-SNAPSHOT`


---

## Secrets

None are committed. `connector-secrets.txt` and `.env` are git-ignored. Fill
them locally from your own rotated credentials.
