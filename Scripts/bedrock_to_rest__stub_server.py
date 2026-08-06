"""Local stand-in for the blueprint's six AWS Bedrock AI calls.

Despite standing in for Bedrock, this speaks plain REST — it never implements
the Bedrock protocol. What it reproduces is the Bedrock *response envelope*
the blueprint's FEEL expects:

    { "body": { "content": [ {...}, { "text": "```json{...}```" } ] } }

The tasks read body.content[1].text, strip the ```json fences and parse. By
returning that exact shape, no downstream FEEL expression had to change.

Routes (GET or POST): /planner /gdpr /iso /threat /short_desc /explanation
Run: python3 ai_stub_server.py    (listens on :9997)
"""
from flask import Flask, jsonify
import json
app = Flask(__name__)

def envelope(t):
    return {"body": {"content": [{"type":"text","text":""},{"type":"text","text":t}]}}
def fenced(o):
    return "```json\n" + json.dumps(o, ensure_ascii=False) + "\n```"

P = {"tools":["threat_intel_lookup","asset_lookup","check_gdpr_relevance"],
     "reasoning":"TEST FIXTURE synthetic plan.","priority":"high"}
G = {"gdpr_relevant":True,"personal_data_categories":["synthetic-customer-records"],
     "reporting_obligation_72h":True,"assessment":"TEST FIXTURE synthetic GDPR assessment."}
I = {"iso_controls":["A.5.24","A.5.25","A.8.16"],"iso_status":"deviation_detected",
     "report":"TEST FIXTURE synthetic ISO 27001 evaluation."}
T = {"threat_level":"elevated","indicators":["198.51.100.46","injection-pattern"],
     "interpretation":"TEST FIXTURE synthetic threat interpretation."}
S = {"short_description":"TEST FIXTURE Suspected injection against TEST-DB-02 (synthetic).","severity":"high"}
E = {"explanation":"TEST FIXTURE synthetic analyst explanation.","confidence":0.82}

M = ["GET","POST"]
@app.route("/health", methods=M)
def h(): return jsonify({"status":"ok"}), 200
@app.route("/planner", methods=M)
def p(): return jsonify(envelope(fenced(P))), 200
@app.route("/gdpr", methods=M)
def g(): return jsonify(envelope(fenced(G))), 200
@app.route("/iso", methods=M)
def i(): return jsonify(envelope(fenced(I))), 200
@app.route("/threat", methods=M)
def t(): return jsonify(envelope(fenced(T))), 200
@app.route("/short_desc", methods=M)
def s(): return jsonify(envelope(fenced(S))), 200
@app.route("/explanation", methods=M)
def e(): return jsonify(envelope(fenced(E))), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9997)
