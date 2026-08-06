#!/usr/bin/env python3
"""
SOC investigation tools exposed as an MCP server (Streamable HTTP).

Replaces the ad-hoc subprocess's three hard-coded BPMN elements with real MCP
tools that the AI Agent connector discovers at runtime. Tool selection is no
longer a list of element-ID strings that the model must emit exactly; the agent
reads these schemas and calls them by contract.

  threat_intel_lookup   REAL   -> internetdb.shodan.io (free, no API key)
  asset_lookup          stub   -> synthetic TEST-* inventory
  check_gdpr_relevance  stub   -> deterministic verdict from keywords

Runs on the host, reached from the connectors container via
host.docker.internal (already in extra_hosts).

    pip3 install "mcp>=1.28,<2" --break-system-packages
    python3 soc_mcp_server.py

The <2 pin is required. MCP Python SDK 2.0 renamed FastMCP to MCPServer with no
alias and no deprecation shim, and `pip install mcp` now resolves to the 2.x
line. Without the upper bound this file fails at import with
ModuleNotFoundError: No module named 'mcp.server.fastmcp'.

Endpoint: http://host.docker.internal:9996/mcp
"""

import json
import logging
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("soc-mcp")

mcp = FastMCP("soc-tools", host="0.0.0.0", port=9996)

# internetdb.shodan.io is free and needs no API key, but it rejects the default
# urllib User-Agent with 403. Identify the client explicitly.
SHODAN_BASE = "https://internetdb.shodan.io"
USER_AGENT = "soc-mcp-server/1.0 (Camunda agentic SOC demo)"


# --------------------------------------------------------------------------
# Synthetic fixtures. RFC 5737 documentation IPs, TEST-* hostnames.
# --------------------------------------------------------------------------

ASSETS = {
    "TEST-DB-02": {
        "hostname": "TEST-DB-02",
        "asset_class": "Database Server",
        "business_criticality": "HIGH",
        "owner_unit": "Data Platform Operations",
        "environment": "TEST",
        "contains_personal_data": True,
        "data_categories": ["customer_master", "billing_address"],
    },
    "TEST-CRM-02": {
        "hostname": "TEST-CRM-02",
        "asset_class": "CRM Application",
        "business_criticality": "HIGH",
        "owner_unit": "Sales Operations",
        "environment": "TEST",
        "contains_personal_data": True,
        "data_categories": ["contact_details", "sales_history"],
    },
    "TEST-AUTH-01": {
        "hostname": "TEST-AUTH-01",
        "asset_class": "Authentication Server",
        "business_criticality": "CRITICAL",
        "owner_unit": "Identity and Access Management",
        "environment": "TEST",
        "contains_personal_data": False,
        "data_categories": [],
    },
}

GDPR_TRIGGERS = [
    # German — matches the incident_topic strings the producer emits
    "kundendatenbank",
    "kundendaten",
    "personenbezogen",
    "datenabfluss",
    "datenschutz",
    "dsgvo",
    "crm",
    # English equivalents, for prompts written in English
    "customer",
    "personal data",
    "pii",
    "gdpr",
]


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------

@mcp.tool()
def threat_intel_lookup(ip: str) -> dict:
    """Look up an external IP address against open threat intelligence.

    Returns the open ports, hostnames, CPEs, tags and known CVEs that public
    internet scanning has observed for this address. Use this when an incident
    references an external IP and you need to know whether that address is
    already known to be exposed or malicious.

    Args:
        ip: The external IPv4 address to look up, e.g. "198.51.100.46".
    """
    url = f"{SHODAN_BASE}/{ip}"
    log.info("threat_intel_lookup -> %s", url)
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            # Explicit UA is required. urllib defaults to "Python-urllib/3.x",
            # which internetdb.shodan.io answers with 403 while the identical
            # request from curl returns normally.
            "User-Agent": USER_AGENT,
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        log.info("threat_intel_lookup <- %s ports=%s vulns=%d",
                 ip, data.get("ports", []), len(data.get("vulns", [])))
        return {
            "ip": ip,
            "source": "internetdb.shodan.io",
            "found": True,
            "ports": data.get("ports", []),
            "hostnames": data.get("hostnames", []),
            "tags": data.get("tags", []),
            "vulns": data.get("vulns", []),
            "cpes": data.get("cpes", []),
        }
    except urllib.error.HTTPError as e:
        if e.code in (403, 404, 429):
            log.info("threat_intel_lookup <- %s no record (HTTP %s)", ip, e.code)
            return {
                "ip": ip,
                "source": "internetdb.shodan.io",
                "found": False,
                "http_status": e.code,
                "note": (
                    "No public scan record for this address. RFC 5737 "
                    "documentation ranges (198.51.100.0/24, 192.0.2.0/24) are "
                    "never scanned, so a negative result is expected for the "
                    "synthetic fixtures used in this demo. A 403 or 429 may "
                    "also indicate the free endpoint refused or throttled the "
                    "request."
                ),
            }
        log.warning("shodan HTTP %s for %s", e.code, ip)
        return {"ip": ip, "found": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        log.warning("shodan lookup failed for %s: %s", ip, e)
        return {"ip": ip, "found": False, "error": str(e)}


@mcp.tool()
def asset_lookup(hostname: str) -> dict:
    """Resolve an internal hostname to its asset record.

    Returns the asset class, business criticality, owning organizational unit
    and whether the system holds personal data. Use this when an incident names
    an internal system and you need to judge blast radius or find an owner.

    Args:
        hostname: Internal system identifier, e.g. "TEST-DB-02".
    """
    key = (hostname or "").strip().upper()
    log.info("asset_lookup -> %s", key)
    if key in ASSETS:
        return {"found": True, **ASSETS[key]}
    return {
        "found": False,
        "hostname": key,
        "note": "Not present in the asset inventory.",
        "known_hostnames": sorted(ASSETS),
    }


@mcp.tool()
def check_gdpr_relevance(incident_topic: str) -> dict:
    """Assess whether a security incident engages GDPR obligations.

    Returns a YES/NO verdict, the matched indicators and the reasoning. Use this
    before any decision about notification or ticket routing, since GDPR
    relevance changes both the deadline and the responsible unit.

    Args:
        incident_topic: The incident description to assess.
    """
    topic = (incident_topic or "").lower()
    hits = [t for t in GDPR_TRIGGERS if t in topic]
    relevant = bool(hits)
    log.info("check_gdpr_relevance -> %s (hits=%s)", relevant, hits)
    return {
        "gdpr_relevance": "YES" if relevant else "NO",
        "matched_indicators": hits,
        "reasoning": (
            "The incident references personal or customer data, so Art. 33 "
            "notification duties may apply and the 72-hour clock should be "
            "assumed to run."
            if relevant else
            "No indication that personal data is involved. Handle under normal "
            "security incident procedure."
        ),
        "notification_deadline_hours": 72 if relevant else None,
    }


if __name__ == "__main__":
    log.info("SOC MCP server on http://0.0.0.0:9996/mcp")
    log.info("tools: threat_intel_lookup, asset_lookup, check_gdpr_relevance")
    mcp.run(transport="streamable-http")
