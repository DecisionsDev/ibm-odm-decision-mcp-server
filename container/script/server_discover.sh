#!/usr/bin/env bash
if [[ -d /mcp-certs/tls/tls-enabled ]]; then
  SCHEME="https"
else
  SCHEME="http"
fi
curl --insecure ${CURL_OPTS} \
    -H "mcp-method: server/discover" \
    -H "mcp-protocol-version: 2026-07-28" \
    -H "Accept: application/json,text/event-stream" \
    -H "Content-Type: application/json" \
    ${SCHEME}://localhost:${PORT}${MOUNT_PATH} \
    -d '{
  "jsonrpc": "2.0",
  "id": "server-discover-probe-1",
  "method": "server/discover",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientInfo": {
        "name": "mcp-inspector",
        "version": "0.0.0"
      },
      "io.modelcontextprotocol/clientCapabilities": {
        "sampling": {},
        "elicitation": {
          "form": {},
          "url": {}
        },
        "roots": {
          "listChanged": true
        },
        "tasks": {
          "list": {},
          "cancel": {},
          "requests": {
            "sampling": {
              "createMessage": {}
            },
            "elicitation": {
              "create": {}
            }
          }
        },
        "extensions": {
          "io.modelcontextprotocol/tasks": {},
          "io.modelcontextprotocol/ui": {
            "mimeTypes": [
              "text/html;profile=mcp-app"
            ]
          }
        }
      }
    }
  }
}'