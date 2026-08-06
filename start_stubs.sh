#!/bin/bash
cd "$(dirname "$0")"
for p in 9995 9996 9997 9998; do
  lsof -tiTCP:$p -sTCP:LISTEN | xargs -r kill 2>/dev/null
done
sleep 1
nohup python3 llm_stub_server.py              > llm.log      2>&1 &
nohup python3 soc_mcp_server.py               > mcp.log      2>&1 &
nohup python3 bedrock_to_rest__stub_server.py > bedrock.log  2>&1 &
nohup python3 incident_stub_server.py         > incident.log 2>&1 &
disown -a
sleep 2
echo "--- listening ---"
lsof -iTCP:9995 -iTCP:9996 -iTCP:9997 -iTCP:9998 -sTCP:LISTEN
