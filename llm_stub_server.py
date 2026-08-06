#!/usr/bin/env python3
"""
OpenAI-compatible chat-completions stub for the Camunda AI Agent connector.

Same principle as bedrock_to_rest__stub_server.py, one layer up: it fakes only
the model's output. Camunda's agent loop, MCP tool discovery, tool dispatch and
result correlation all run for real. Swapping in a live provider is two fields
in the properties panel, with no BPMN change.

Why it is adaptive rather than hard-coded: the tool names the agent advertises
are assembled by the MCP client and may be namespaced by client ID. Instead of
guessing that convention, the stub reads the "tools" array on each request and
calls back whatever it was offered, matching on suffix. That makes it immune to
naming changes in the connector.

Loop control, which a stateless stub gets wrong:
  turn 1  -> messages carry no tool results -> return tool_calls  (agent runs tools)
  turn 2+ -> messages carry tool results    -> return final text  (agent stops)
A stub that always returns tool_calls will spin until the agent's iteration cap.

    pip3 install flask --break-system-packages
    python3 llm_stub_server.py

Endpoint for the AI Agent connector:
    Provider:     OpenAI Compatible
    API endpoint: http://host.docker.internal:9995/v1
    Model:        soc-stub-1
    API key:      any non-empty string
"""

import json
import logging
import re
import time
import uuid

from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("llm-stub")

app = Flask(__name__)

# Tool suffixes this stub knows how to drive, and how to fill their arguments.
WANTED = ["threat_intel_lookup", "asset_lookup", "check_gdpr_relevance"]

IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
HOST_RE = re.compile(r"\bTEST-[A-Z0-9-]+\b", re.IGNORECASE)

# Used only when the user prompt carries no IP / hostname / text at all.
# RFC 5737 documentation range, TEST-* inventory names.
FALLBACK_IP = "198.51.100.46"
FALLBACK_HOST = "TEST-DB-02"
FALLBACK_TOPIC = "Unspecified security incident"


def collect_text(messages):
    """Flatten USER message content only, tolerating content-block arrays.

    The role filter matters. Camunda's AI Agent connector prepends a long
    default system prompt ("You are **TaskAgent**, a helpful, generic chat
    agent..."). Including it meant tool arguments were built from the system
    prompt instead of the incident, so check_gdpr_relevance received boilerplate
    and could never match a real indicator. Only the user turns describe the
    incident.
    """
    out = []
    for m in messages or []:
        if m.get("role") != "user":
            continue
        c = m.get("content")
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, list):
            for blk in c:
                if isinstance(blk, dict) and blk.get("type") == "text":
                    out.append(blk.get("text", ""))
    return "\n".join(out).strip()


def offered_tools(body):
    """Map wanted suffix -> the exact tool name the agent advertised."""
    found = {}
    for t in body.get("tools") or []:
        name = (t.get("function") or {}).get("name") or t.get("name")
        if not name:
            continue
        for w in WANTED:
            if name.endswith(w) or w in name:
                found.setdefault(w, name)
    return found


def has_tool_results(messages):
    """True once the agent has fed tool output back into the conversation."""
    for m in messages or []:
        if m.get("role") == "tool":
            return True
        if m.get("role") == "user" and isinstance(m.get("content"), list):
            for blk in m["content"]:
                if isinstance(blk, dict) and blk.get("type") in (
                    "tool_result", "toolResult"
                ):
                    return True
    return False


def build_tool_calls(available, text):
    """Emit one call per available tool, with arguments read from the incident."""
    if not text:
        log.warning(
            "no user text found - falling back to defaults. Check that the "
            "User prompt is set on the AI Agent element."
        )

    ip_match = IP_RE.search(text)
    host_match = HOST_RE.search(text)
    ip = ip_match.group(0) if ip_match else FALLBACK_IP
    hostname = host_match.group(0).upper() if host_match else FALLBACK_HOST
    topic = text[:500] if text else FALLBACK_TOPIC

    log.info("extracted ip=%s hostname=%s topic=%r", ip, hostname, topic[:80])

    args_for = {
        "threat_intel_lookup": {"ip": ip},
        "asset_lookup": {"hostname": hostname},
        "check_gdpr_relevance": {"incident_topic": topic},
    }

    calls = []
    for suffix, actual_name in available.items():
        calls.append({
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {
                "name": actual_name,
                "arguments": json.dumps(args_for[suffix], ensure_ascii=False),
            },
        })
    return calls


def envelope(model, message, finish_reason):
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:20]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


FINAL_SUMMARY = (
    "Investigation complete. The external address was checked against open "
    "threat intelligence, the affected internal system was resolved against the "
    "asset inventory, and the incident was assessed for GDPR relevance. The "
    "findings from all three tools are recorded in the agent context and are "
    "ready for analyst validation."
)


@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    body = request.get_json(force=True, silent=True) or {}
    model = body.get("model", "soc-stub-1")
    messages = body.get("messages", [])
    available = offered_tools(body)

    log.info(
        "turn: messages=%d offered=%s results_present=%s",
        len(messages), list(available), has_tool_results(messages),
    )

    if available and not has_tool_results(messages):
        calls = build_tool_calls(available, collect_text(messages))
        log.info("-> requesting %d tool call(s)", len(calls))
        return jsonify(envelope(
            model,
            {"role": "assistant", "content": None, "tool_calls": calls},
            "tool_calls",
        ))

    log.info("-> final answer, ending agent loop")
    return jsonify(envelope(
        model,
        {"role": "assistant", "content": FINAL_SUMMARY},
        "stop",
    ))


@app.route("/v1/models", methods=["GET"])
def models():
    return jsonify({
        "object": "list",
        "data": [{"id": "soc-stub-1", "object": "model", "owned_by": "local-stub"}],
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    log.info("LLM stub on http://0.0.0.0:9995/v1/chat/completions")
    app.run(host="0.0.0.0", port=9995, threaded=True)
