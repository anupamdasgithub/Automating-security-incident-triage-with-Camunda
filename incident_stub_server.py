"""
Local stub that replaces the AWS Bedrock scenario-generator call for
end-to-end testing of the incident pipeline.

Returns clearly-synthetic, labeled test fixtures keyed by incident_topic.
- Documentation IPs only (RFC 5737: 192.0.2.0/24, 198.51.100.0/24)
- Obviously-fake hostnames (TEST-*), fake user IDs
- No real attack methodology, no "ignore your policies" framing

Run:  python incident_stub_server.py   (listens on :9998)
Health: GET /health
Invoke: POST /invoke  { "incident_topic": "<topic string>" }
"""
from flask import Flask, request, jsonify
import json

app = Flask(__name__)

# Synthetic fixtures. Keys are substrings matched against incident_topic.
# Every value is plainly test data — safe to commit, safe to log, deterministic.
FIXTURES = {
    "Scanaktivität": {
        "incident_type": "external_scan",
        "raw_alert": "TEST FIXTURE — Port scan observed from 192.0.2.10 against "
                     "host TEST-WEB-01. 40 connection attempts across ports "
                     "22/80/443 in 60s. Synthetic sample for pipeline testing.",
    },
    "Security Scan": {  # ISO_IGNORE — pre-approved, should be filtered as non-incident
        "incident_type": "approved_scan",
        "raw_alert": "TEST FIXTURE — Scheduled vulnerability scan from 192.0.2.20, "
                     "change ticket CHG-TEST-0001, approved window. Expected "
                     "activity, no incident. Synthetic sample.",
    },
    "Proxy/VPN": {
        "incident_type": "anonymized_traffic",
        "raw_alert": "TEST FIXTURE — Traffic from 198.51.100.45 flagged as "
                     "anonymizing proxy against TEST-APP-02. Synthetic sample.",
    },
    "Kundendatenbank": {  # ISO_GDPR
        "incident_type": "data_access",
        "raw_alert": "TEST FIXTURE — Unusual read on TEST-DB-01 (fake dataset: "
                     "synthetic customer records, user testuser-042). GDPR "
                     "relevance flag set for pipeline testing. Synthetic sample.",
    },
    "CRM-System": {  # ISO_GDPR_Asset
        "incident_type": "data_exfil_suspected",
        "raw_alert": "TEST FIXTURE — Elevated export volume from TEST-CRM-02 by "
                     "user testuser-108. Synthetic contact records only. "
                     "Synthetic sample for asset+GDPR path.",
    },
    "mehrere interne Systeme": {  # ISO_THREAT_ASSET
        "incident_type": "multi_host_contact",
        "raw_alert": "TEST FIXTURE — 198.51.100.46 contacted TEST-SRV-01/02/03. "
                     "Synthetic sample for threat+asset correlation.",
    },
    "Authentifizierungsserver": {  # ISO_ASSET
        "incident_type": "host_anomaly",
        "raw_alert": "TEST FIXTURE — TEST-AUTH-01 shows elevated CPU and an "
                     "unrecognized process (synthetic). Integrity check path. "
                     "Synthetic sample.",
    },
}

DEFAULT = {  # ISO_THREAT_ASSET_GDPR combined path
    "incident_type": "combined_multi_domain",
    "raw_alert": "TEST FIXTURE — Repeated access from 198.51.100.46 to TEST-DB-02 "
                 "resembling injection pattern; synthetic customer fields touched. "
                 "Exercises all downstream tools. Synthetic sample only.",
}


def pick_fixture(topic: str):
    for key, val in FIXTURES.items():
        if key.lower() in (topic or "").lower():
            return val
    return DEFAULT


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/invoke", methods=["POST"])
def invoke():
    body = request.get_json(force=True, silent=True) or {}
    topic = body.get("incident_topic", "")
    fixture = pick_fixture(topic)

    # Return the fixture fields at the top level so the REST connector's
    # result expression is trivial:
    #   response.body.incident_type / response.body.raw_alert
    # (We also keep a Bedrock-style content[] block for reference/teaching,
    #  but the pipeline reads the flat fields.)
    payload = {
        "incident_type": fixture["incident_type"],
        "raw_alert": fixture["raw_alert"],
        "content": [
            {"type": "text", "text": json.dumps(fixture, ensure_ascii=False)}
        ],
    }
    # The REST connector wraps the HTTP response as { statusCode, headers, body }.
    # Flask returning this dict as JSON becomes response.body downstream.
    return jsonify(payload), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9998)
