# Copyright contributors to the IBM ODM MCP Server project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional, Any
from mcp.server.mcpserver.context import Context
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from mcp_types import Tool, Resource, CallToolResult, TextContent
from mcp_types.version import MODERN_PROTOCOL_VERSIONS
from mcp.server import MCPServer
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.session import ServerSession
from mcp.server.mcpserver.exceptions import ToolError, ResourceError, ResourceNotFoundError
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.shared.subscriptions import ToolsListChanged
from pydantic import AnyUrl
import logging
import urllib3
import uvicorn

from decision_mcp_server.DecisionServiceDescription import DecisionServiceDescription
from decision_mcp_server.Credentials import Credentials
from decision_mcp_server.DecisionServerManager import DecisionServerManager
from decision_mcp_server.config import INSTRUCTIONS, BASE_DIR
from decision_mcp_server.ExecutionToolTrace import ExecutionToolTrace, DiskTraceStorage
from decision_mcp_server.utils.ssl_utils import merge_ssl_cert_paths
import argparse
import os
import sys
import socket

class DecisionMCPServer:
    MASKED_VALUE = "*****"
    # Seconds to wait before the first refresh of the tools when running in a pod
    POD_INITIAL_REFRESH_DELAY = 300
    # Startup arguments (argparse destination names) whose value must not be disclosed by the healthcheck endpoint
    SENSITIVE_ARGUMENTS = frozenset({"username", "password", "zenapikey",
                                     "client_id", "client_secret", "scope",
                                     "pkjwt_key_password", "mtls_key_password", "https_key_password"})
    # Environment variables read by the MCP server, with a flag telling whether their value is sensitive
    ENVIRONMENT_VARIABLES = {
        # sensitive
        "ODM_USERNAME": True, "ODM_PASSWORD": True, "ZENAPIKEY": True,
        "CLIENT_ID": True, "CLIENT_SECRET": True, "SCOPE": True,
        "PKJWT_KEY_PASSWORD": True, "MTLS_KEY_PASSWORD": True, "HTTPS_KEY_PASSWORD": True,
        # not-sensitive
        "ODM_URL": False, "ODM_RUNTIME_URL": False, "TOKEN_URL": False,
        "VERIFY_SSL": False, "VERIFY_SSL_HOSTNAME": False,
        "SSL_CERT_PATH": False,
        "PKJWT_CERT_PATH": False, "PKJWT_KEY_PATH": False,
        "MTLS_CERT_PATH": False, "MTLS_KEY_PATH": False,
        "HTTPS_CERT_PATH": False, "HTTPS_KEY_PATH": False,
        "CONSOLE_AUTH_TYPE": False, "RUNTIME_AUTH_TYPE": False,
        "TRANSPORT": False, "HOST": False, "PORT": False, "MOUNT_PATH": False,
        "LOG_LEVEL": False, "TRACES_DIR": False, "TRACE_ENABLE": False, "TRACE_MAXSIZE": False,
        "DEDICATED_RUNTIMES": False, "RUNNING_IN_POD": False,
        "TOOLS_REFRESH_PERIOD": False, "TOOLS_REFRESH_MIN_INTERVAL": False,
    }

    def __init__(self, console_credentials: Credentials, runtime_credentials: Credentials,
                 transport: Optional[str] = 'stdio', host: Optional[str] = '0.0.0.0', port: int = 3000, path: Optional[str] = '/mcp',
                 traces_dir: Optional[str] = None, trace_enable: bool = False, trace_maxsize: int = 50,
                 dedicated_runtimes: Optional[list[tuple[str, str]]] = None,
                 https_cert_path: Optional[str] = None, https_key_path: Optional[str] = None, https_key_password: Optional[str] = None,
                 startup_args: Optional[dict[str, Any]] = None,
                 tools_refresh_period: int = 300,
                 tools_refresh_min_interval: int = 20,
                 ):
        # Get logger for this class
        self.logger = logging.getLogger(__name__)
        
        self.notes: dict[str, str] = {}
        self.repository: dict[str, DecisionServiceDescription] = {}
        self.server: Optional[MCPServer] = None

        # Background refresh of the tools: period in seconds (0 or less disables it)
        self.tools_refresh_period = tools_refresh_period
        self.tools_refresh_min_interval = tools_refresh_min_interval
        self._last_tools_refresh: Optional[float] = None
        self._legacy_session: Optional[ServerSession] = None  # session of the legacy client (stdio only), to notify it that the tools changed
        self._refresh_stop = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None  # event loop serving the requests, captured by the lifespan of the MCP server

        # Store trace configuration
        self.trace_enable = trace_enable
        self.trace_maxsize = trace_maxsize
        # Disable Warning
        urllib3.disable_warnings()

        # Set up trace storage with configured parameters if tracing is enabled
        # If traces_dir is None, DiskTraceStorage will use the default path in user's home directory
        if self.trace_enable:
            self.execution_traces = DiskTraceStorage(storage_dir=traces_dir, max_traces=self.trace_maxsize)
        else:
            self.execution_traces = None
            self.logger.info("Trace storage is disabled")
        
        self.manager = None
        self.console_credentials = console_credentials
        self.runtime_credentials = runtime_credentials
        # Build a lookup dict: ruleset path prefix -> dedicated Credentials object.
        # The dedicated runtime shares all auth settings with runtime_credentials,
        # only the base URL differs.
        # Multiple paths may point to the same URL: create one Credentials object per
        # unique URL and reuse it so that auth state (tokens, sessions) is not duplicated.
        self.dedicated_runtime_credentials: dict[str, Credentials] = {}
        _url_to_credentials: dict[str, Credentials] = {}
        for path_prefix, dedicated_url in (dedicated_runtimes or []):
            if dedicated_url not in _url_to_credentials:
                _url_to_credentials[dedicated_url] = Credentials(
                    odm_url=dedicated_url,
                    token_url=runtime_credentials.token_url,
                    scope=runtime_credentials.scope,
                    client_id=runtime_credentials.client_id,
                    client_secret=runtime_credentials.client_secret,
                    pkjwt_cert_path=runtime_credentials.pkjwt_cert_path,
                    pkjwt_key_path=runtime_credentials.pkjwt_key_path,
                    pkjwt_key_password=runtime_credentials.pkjwt_key_password,
                    username=runtime_credentials.username,
                    password=runtime_credentials.password,
                    zenapikey=runtime_credentials.zenapikey,
                    verify_ssl=runtime_credentials.verify_ssl,
                    verify_ssl_hostname=runtime_credentials.verify_ssl_hostname,
                    ssl_cert_path=runtime_credentials.ssl_cert_path,
                    mtls_cert_path=runtime_credentials.mtls_cert_path,
                    mtls_key_path=runtime_credentials.mtls_key_path,
                    mtls_key_password=runtime_credentials.mtls_key_password,
                )
            self.dedicated_runtime_credentials[path_prefix] = _url_to_credentials[dedicated_url]
            self.logger.info("Dedicated runtime registered: %s -> %s", path_prefix, dedicated_url)

        self.transport = transport
        self.host      = host
        self.port      = port
        self.path      = path

        self.https_cert_path    = https_cert_path
        self.https_key_path     = https_key_path
        self.https_key_password = https_key_password
        self.startup_args: dict[str, Any] = startup_args if startup_args is not None else {}
        if bool(self.https_cert_path) != bool(self.https_key_path):
            raise ValueError("HTTPS requires both a certificate (--https-cert-path) and a private key (--https-key-path)")

    async def list_resources(self) -> list[Resource]:
        return [
            Resource(
                uri=f"decisionservice://internal/{name}",
                name=f"DecisionService: {name}",
                description=f"Decision Service: {name}",
                mimeType="text/plain",
            )
            for name in self.repository.keys()
        ]

    async def read_resource(self, uri: AnyUrl | str, context: Context | None = None) -> list[ReadResourceContents]:
        uri = AnyUrl(str(uri))
        if uri.scheme != "decisionservice":
            raise ResourceError(f"Unsupported URI scheme: {uri.scheme}")

        name = (uri.path or "").lstrip("/")
        if name not in self.repository:
            raise ResourceNotFoundError(f"DecisionService not found: {name}")
        return [ReadResourceContents(content=str(self.repository[name].__dict__), mime_type="text/plain")]

    def _fetch_tools(self) -> tuple[list[Tool], dict[str, DecisionServiceDescription]]:
        """Fetches the tools from the ODM Decision Server.

        Returns:
            A tuple with the list of tools and the repository (tool name -> decision service description).
        """
        # Ensure manager is initialized before using it
        if self.manager is None:
            self.manager = DecisionServerManager(console_credentials=self.console_credentials,
                                                 runtime_credentials=self.runtime_credentials)

        rulesets = self.manager.fetch_rulesets()
        repository = self.manager.generate_tools_format(rulesets)
        tools = [decisionService.tool_description for decisionService in repository.values()]
        return tools, repository

    async def list_tools(self) -> list[Tool]:
        self.logger.info("Listing ODM tools")
        if self.refresh_tools_allowed():
            return self.refresh_tools()
        return [decisionService.tool_description for decisionService in self.repository.values()]

    def refresh_tools(self) -> list[Tool]:
        """Fetches the tools from ODM and notifies clients if the toolset has changed.

        Returns:
            list[Tool]: The updated list of tools.
        """
        tools, repository = self._fetch_tools()
        if repository != self.repository:
            self.repository = repository
            if self._last_tools_refresh is not None:
                self._notify_tools_changed()
        self._last_tools_refresh = time.monotonic()
        return tools

    def refresh_tools_allowed(self) -> bool:
        """Tells whether refreshing the tools is allowed according to `tools_refresh_min_interval`.

        Returns:
            bool: True if refreshing the tools is allowed, False otherwise.
        """
        if self.tools_refresh_min_interval < 0:
            return False
        if self._last_tools_refresh is None or self.tools_refresh_min_interval == 0:
            return True
        return (time.monotonic() - self._last_tools_refresh) >= self.tools_refresh_min_interval

    def _notify_tools_changed(self) -> None:
        """Notifies the MCP clients that the tools changed.

        The modern clients are notified through a `tools/list_changed` event published on the subscription bus of
        the MCP server. The legacy client (stdio only, see `_capture_legacy_session`) is notified through its session.
        Both must be used from the event loop serving the requests, which is captured by `_lifespan`
        when the MCP server starts serving. Before that, no client can be listening, so nothing is published.
        """
        if self._loop is None or self.server is None:
            return
        try:
            if self.transport == "stdio" and self._legacy_session is not None:
                # the MCP server runs locally and the client is legacy
                self.logger.info("The tools changed. Notifying the MCP client.")
                asyncio.run_coroutine_threadsafe(self._send_legacy_tools_changed(self._legacy_session), self._loop)
            else:
                # notify Modern clients
                self.logger.info("The tools changed. Notifying the modern MCP clients.")
                asyncio.run_coroutine_threadsafe(self.server._subscriptions.publish(ToolsListChanged()), self._loop)
        except (RuntimeError, AttributeError) as e:
            self.logger.warning("The clients could not be notified that the tools changed: %s", e)
        except Exception:
            self.logger.exception("Unexpected error while notifying the clients that the tools changed")

    async def _send_legacy_tools_changed(self, session: ServerSession) -> None:
        """Sends a `notifications/tools/list_changed` to the legacy client on the standalone channel of its connection.

        Args:
            session: The session of the legacy client, captured by `_capture_legacy_session`.
        """
        try:
            await session.send_tool_list_changed()
        except Exception as e:
            self.logger.warning("The legacy client could not be notified that the tools changed: %s", e)
            if self._legacy_session is session:
                self._legacy_session = None

    async def _capture_legacy_session(self, ctx: ServerRequestContext, call_next: CallNext) -> HandlerResult:
        """Middleware keeping the session of the legacy client, so that it can be notified outside of a request.

        Only registered with the stdio transport, where a single client talks to the process over a single connection
        for the whole life of the process. The standalone channel of that connection, which the session sends
        notifications on, is then valid outside of a request. With the HTTP transports, the connection is
        created for each request (stateless), so there is no channel to reach the client between requests.
        The modern clients are not concerned: they are notified through the subscription bus.

        Args:
            ctx: The context of the message.
            call_next: Invokes the rest of the chain.

        Returns:
            The result of the message.
        """
        if ctx.protocol_version not in MODERN_PROTOCOL_VERSIONS:
            self._legacy_session = ctx.session
        return await call_next(ctx)

    def is_running_in_pod(self) -> bool:
        """ Tells whether the MCP server runs in a pod. """
        return os.getenv("RUNNING_IN_POD", "False") == "True" and self.transport == "streamable-http"

    def _tools_refresh_loop(self) -> None:
        """ Refreshes the tools periodically until stopped. """
        delay = float(self.POD_INITIAL_REFRESH_DELAY if self.is_running_in_pod() else self.tools_refresh_period)
        while not self._refresh_stop.wait(delay):
            delay = float(self.tools_refresh_period)
            try:
                self.refresh_tools()
            except Exception as e:
                self.logger.warning("Failed to refresh the tools: %s", e)

    def start_tools_refresh(self) -> None:
        """Starts the daemon thread refreshing the tools periodically, unless `tools_refresh_period` is 0 or less."""
        if self.tools_refresh_period <= 0:
            self.logger.info("Periodic refresh of the tools is disabled")
            return
        self.logger.info("Refreshing the tools every %d seconds", self.tools_refresh_period)
        threading.Thread(target=self._tools_refresh_loop, name="tools-refresh", daemon=True).start()

    async def call_tool(self, name: str, arguments: dict | None, context: Context) -> CallToolResult:
        if not self.repository or (self.repository.get(name) is None and self.refresh_tools_allowed()):
            self.refresh_tools()

        if self.repository.get(name) is None:
            self.logger.error("Tool not found: %s", name)
            raise ToolError(f"Unknown tool: {name}")

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Calling tool %s with arguments: %s", name, arguments)
        else:
            self.logger.info("Calling tool %s", name)

        # Ensure manager is initialized before using it
        if self.manager is None:
            self.manager = DecisionServerManager(console_credentials=self.console_credentials,
                                                 runtime_credentials=self.runtime_credentials)

        # Resolve dedicated runtime credentials if the ruleset path matches a registered prefix
        ruleset_path = self.repository[name].rulesetPath
        dedicated_credentials = None
        for path_prefix, creds in self.dedicated_runtime_credentials.items():
            if ruleset_path.startswith(path_prefix):
                dedicated_credentials = creds
                self.logger.debug("Using dedicated runtime for path %s: %s", ruleset_path, creds.odm_url)
                break

        try:
            result = self.manager.invokeDecisionService(
                rulesetPath=ruleset_path,
                decisionInputs=arguments,
                runtime_credentials=dedicated_credentials,
            )
            is_error = False
        except ToolError as e:
            raise(e)
        except Exception as e:
            result = str(e)
            is_error = True

        # Extract decision ID and trace if available
        decision_id = None
        decision_trace = None
        
        # Handle dictionary response
        if isinstance(result, dict):
            if result.get("__DecisionID__") is not None:
                decision_id = result["__DecisionID__"]
                del result["__DecisionID__"]
            if result.get("__decisionTrace__") is not None:
                # Ensure decision_trace is a dictionary
                trace_value = result["__decisionTrace__"]
                if isinstance(trace_value, dict):
                    decision_trace = trace_value
                elif isinstance(trace_value, str):
                    # Try to parse JSON string to dict
                    try:
                        decision_trace = json.loads(trace_value)
                    except json.JSONDecodeError:
                        # If not valid JSON, store as dict with original string
                        decision_trace = {"raw_trace": trace_value}
                else:
                    # For any other type, convert to a dictionary
                    decision_trace = {"value": str(trace_value)}
                
                del result["__decisionTrace__"]
                
            response_text = json.dumps(result, indent=2, ensure_ascii=False)
        else:
            # Handle non-dict response (string, etc)
            response_text = str(result)

        # Create and store execution trace if tracing is enabled
        if self.trace_enable and self.execution_traces is not None:
            trace = ExecutionToolTrace(
                tool_name=name,
                ruleset_path=self.repository[name].rulesetPath,
                inputs=arguments or {},
                results=result,
                decision_id=decision_id,
                decision_trace=decision_trace
            )
            trace_id = self.execution_traces.add(trace)
            
            # Log the creation of the trace
            self.logger.info(f"Created execution trace with ID: {trace_id}")
        else:
            self.logger.debug("Trace storage is disabled, not creating execution trace")

        return CallToolResult(
                    content=[
                        TextContent(
                            type="text", 
                            text=response_text,
                        )
                    ],
                    is_error=is_error,
                )
        
    # Add a new method to list execution traces
    async def list_execution_traces(self) -> list[Resource]:
        """Return a list of execution traces as resources."""
        if not self.trace_enable or self.execution_traces is None:
            self.logger.info("Trace storage is disabled, returning empty list")
            return []
            
        trace_metadata = self.execution_traces.get_all_metadata()
        return [
            Resource(
                uri=f"trace://{metadata['id']}",
                name=f"Execution Trace: {metadata['tool_name']}",
                description=f"Trace executed at {metadata['timestamp']}",
                mimeType="application/json",
            )
            for metadata in trace_metadata
        ]
    
    # Add a method to get a specific execution trace
    async def get_execution_trace(self, trace_id: str) -> Optional[ExecutionToolTrace]:
        """Get a specific execution trace by ID."""
        if not self.trace_enable or self.execution_traces is None:
            self.logger.info("Trace storage is disabled, cannot retrieve trace")
            return None
            
        return self.execution_traces.get(trace_id)

    def get_config(self) -> dict[str, dict[str, Any]]:
        """Builds the startup configuration of the MCP server, with the sensitive values masked.

        Unset values (None) are omitted. Set sensitive values are replaced by `*****`.

        Returns:
            A dict with the keys `arguments` (startup arguments) and `environment`
            (environment variables read by the MCP server).
        """
        arguments = {name: (self.MASKED_VALUE if name in self.SENSITIVE_ARGUMENTS else value)
                     for name, value in self.startup_args.items() if value is not None}
        environment = {name: (self.MASKED_VALUE if sensitive else os.environ[name])
                       for name, sensitive in self.ENVIRONMENT_VARIABLES.items() if name in os.environ}
        return {"arguments": arguments, "environment": environment}

    def register_healthcheck(self) -> None:
        """Registers the public endpoint `{path}/healthcheck` on the MCP server.

        The endpoint answers HTTP 200 with an empty body. If the query parameter `config` is present,
        the body is a JSON object with the startup arguments and the environment variables (see `get_config`).
        No authentication is required. The route is registered by `start()` right before the MCP server
        begins serving, so the endpoint does not exist (no 200) while the MCP server is not started.
        """
        @self.server.custom_route(f"{self.path.rstrip('/')}/healthcheck", methods=["GET", "HEAD", "OPTIONS"])
        async def healthcheck(request: Request) -> Response:
            if "config" in request.query_params:
                return JSONResponse(self.get_config())
            return Response(status_code=200)

    @asynccontextmanager
    async def _lifespan(self, app: MCPServer) -> AsyncIterator[dict[str, Any]]:
        """Lifespan of the MCP server: captures the event loop serving the requests.

        The refresh thread needs this loop to publish `tools/list_changed` notifications (see
        `_notify_tools_changed`). The SDK enters the lifespan on that loop: once at startup with the
        streamable-http transport, and for each connection with the stdio and sse transports.

        Args:
            app: The MCP server being started.

        Yields:
            An empty lifespan context.
        """
        self._loop = asyncio.get_running_loop()
        yield {}

    def start(self):

        self.manager = DecisionServerManager(console_credentials=self.console_credentials,
                                             runtime_credentials=self.runtime_credentials)

        self.server = MCPServer(name="ibm-odm-decision-mcp-server",
                              instructions=INSTRUCTIONS,
                              lifespan=self._lifespan,
                             )

        # Legacy (handshake) clients only learn that tools can change from the capabilities returned by 'initialize'.
        # MCPServer builds them with no NotificationOptions, so tools.listChanged would be false: default it to true (see notify_client).
        lowlevel_server = self.server._lowlevel_server
        create_initialization_options = lowlevel_server.create_initialization_options
        def create_initialization_options_with_tools_changed(notification_options: NotificationOptions | None = None, *args, **kwargs):
            return create_initialization_options(notification_options or NotificationOptions(tools_changed=True), *args, **kwargs)
        lowlevel_server.create_initialization_options = create_initialization_options_with_tools_changed

        # Legacy clients can only be notified outside of a request with stdio, where the connection outlives the requests
        if self.transport == "stdio":
            self.server.middleware.append(self._capture_legacy_session)

        # Register handlers
        self.server.read_resource  = self.read_resource
        self.server.list_resources = self.list_resources
        self.server.list_tools = self.list_tools
        self.server.call_tool  = self.call_tool

        if self.https_cert_path and self.transport == 'stdio':
            self.logger.warning("HTTPS options are ignored with the stdio transport")

        self.start_tools_refresh()

        # Last step before serving (run() blocks): the healthcheck route only exists once the MCP server is ready to be started
        if self.transport != "stdio":
            scheme = "https" if self.https_cert_path else "http"
            self.logger.info(f"Serving healthcheck on {scheme}://{self.host}:{self.port}{self.path.rstrip('/')}/healthcheck")
            self.register_healthcheck()

        if self.https_cert_path and self.transport != 'stdio':
            self.run_https()
        else:
            self.logger.info(f"Serving MCP server on http://{self.host}:{self.port}{self.path}")
            self.server.run(transport=self.transport,
                            host=self.host,
                            port=self.port,
                            streamable_http_path=self.path,
                            stateless_http=True,
            )

    def run_https(self):
        # FastMCP.run() does not support TLS: serve its ASGI app with uvicorn directly
        if self.transport == 'streamable-http':
            app = self.server.streamable_http_app(
                host=self.host,
                streamable_http_path=self.path,
                stateless_http=True,
            )
        else:
            app = self.server.sse_app(
                host=self.host,
                sse_path=self.path,
            )
        self.logger.info(f"Serving MCP server over HTTPS on https://{self.host}:{self.port}{self.path}")
        uvicorn.run(app,
                    host=self.host,
                    port=self.port,
                    log_level=self.server.settings.log_level.lower(),
                    ssl_certfile=self.https_cert_path,
                    ssl_keyfile=self.https_key_path,
                    ssl_keyfile_password=self.https_key_password)

def _dedicated_runtime_pair(value: str) -> tuple[str, str]:
    """Parse a single 'rulesetPath=serverURL' string into a (path, url) tuple."""
    if '=' not in value:
        raise argparse.ArgumentTypeError(f"Expected rulesetPath=serverURL, got: {value!r}")
    path, _, url = value.partition('=')
    return (path.strip(), url.strip())

def _int_from_env(parser: argparse.ArgumentParser, name: str, default: int) -> int:
    """Read an integer from an environment variable.

    Args:
        parser: The argument parser, used to report an invalid value as a usage error.
        name: The name of the environment variable.
        default: The value returned when the environment variable is not set.

    Returns:
        The integer value of the environment variable, or `default` if it is not set.
    """
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        parser.error(f"environment variable {name} must be an integer, got {os.getenv(name)!r}")

def parse_arguments():
    parser = argparse.ArgumentParser(description="Decision MCP Server")
    parser.add_argument("--url",                                        type=str, default=os.getenv("ODM_URL", "http://localhost:9060/res"), help="ODM service URL")
    parser.add_argument("--runtime-url",        "--runtime_url",        type=str, default=os.getenv("ODM_RUNTIME_URL"), help="ODM service URL")
    parser.add_argument("--username",                                   type=str, default=os.getenv("ODM_USERNAME", "odmAdmin"), help="ODM username (optional)")
    parser.add_argument("--password",                                   type=str, default=os.getenv("ODM_PASSWORD", "odmAdmin"), help="ODM password (optional)")
    parser.add_argument("--zenapikey",                                  type=str, default=os.getenv("ZENAPIKEY"), help="Zen API Key (optional)")
    parser.add_argument("--client-id",          "--client_id",          type=str, default=os.getenv("CLIENT_ID"), help="OpenID Client ID (optional)")
    parser.add_argument("--client-secret",      "--client_secret",      type=str, default=os.getenv("CLIENT_SECRET"), help="OpenID Client Secret (optional)")
    parser.add_argument("--token-url",          "--token_url",          type=str, default=os.getenv("TOKEN_URL"), help="OpenID Connect token endpoint URL (optional)")
    parser.add_argument("--scope",                                      type=str, default=os.getenv("SCOPE", "openid"), help="OpenID Connect scope using when requesting an access token using Client Credentials (optional)")
    parser.add_argument("--verifyssl",          "--verify-ssl",         type=str, default=os.getenv("VERIFY_SSL", "True"), choices=["True", "False"], help="Enable SSL check. Default is True (SSL verification enabled (to check that the server certificate is valid and trusted)).")
    parser.add_argument("--verifyssl-hostname", "--verify-ssl-hostname",type=str, default=os.getenv("VERIFY_SSL_HOSTNAME", "False"), choices=["True", "False"], help="Enable TLS hostname verification. Default is False (TLS hostname verification disabled for compatibility). The TLS hostname verification ensures the MCP server connects to the intended server, not a malicious interceptor by checking if the domain name in the requested URL exactly matches the Common Name (CN) or Subject Alternative Name (SAN) fields in the server’s digital certificate.")
    parser.add_argument("--ssl-cert-path",      "--ssl_cert_path",      type=str, default=os.getenv("SSL_CERT_PATH"), help="Semi-colon or comma-separated list of paths (files or directories) containing trusted SSL certificates. When a directory is specified, only the files with *.pem or *.crt extension are taken into account. If not provided, defaults to the system certificates.")
    parser.add_argument("--pkjwt-cert-path",    "--pkjwt_cert_path",    type=str, default=os.getenv("PKJWT_CERT_PATH"), help="Path to the certificate for PKJWT authentication (mandatory for PKJWT).")
    parser.add_argument("--pkjwt-key-path",     "--pkjwt_key_path",     type=str, default=os.getenv("PKJWT_KEY_PATH"),  help="Path to the private key for PKJWT authentication (mandatory for PKJWT).")
    parser.add_argument("--pkjwt-key-password", "--pkjwt_key_password", type=str, default=os.getenv("PKJWT_KEY_PASSWORD"), help="Password to decrypt the private key for PKJWT authentication. Only needed if the key is password-protected.")
    parser.add_argument("--mtls-cert-path",     "--mtls_cert_path",     type=str, default=os.getenv("MTLS_CERT_PATH"), help="Path to the certificate of the client for mutual TLS authentication (mandatory for mTLS).")
    parser.add_argument("--mtls-key-path",      "--mtls_key_path",      type=str, default=os.getenv("MTLS_KEY_PATH"),  help="Path to the private key of the client for mutual TLS authentication (mandatory for mTLS).")
    parser.add_argument("--mtls-key-password",  "--mtls_key_password",  type=str, default=os.getenv("MTLS_KEY_PASSWORD"), help="Password to decrypt the private key of the client for mutual TLS authentication. Only needed if the key is password-protected.")
    parser.add_argument("--console-auth-type",  "--console_auth_type",  type=str, default=os.getenv("CONSOLE_AUTH_TYPE"), choices=["BASIC", "ZEN", "PKJWT", "SECRET", "NONE"], help="Explicitly set the authentication type for the RES Console")
    parser.add_argument("--runtime-auth-type",  "--runtime_auth_type",  type=str, default=os.getenv("RUNTIME_AUTH_TYPE"), choices=["BASIC", "ZEN", "PKJWT", "SECRET", "NONE"], help="Explicitly set the authentication type for the Decision Server Runtime")

    # arguments useful when running the MCP server in remote mode
    parser.add_argument("--transport",                                  type=str, default=os.getenv("TRANSPORT", "stdio"), choices=["stdio", "streamable-http", "sse"], help="Means of communication of the Decision MCP server: local (stdio) or remote.")
    parser.add_argument("--host",                                       type=str, default=os.getenv("HOST", "0.0.0.0"), help="IP or hostname that the MCP server listens to in remote mode.")
    parser.add_argument("--port",                                       type=int, default=_int_from_env(parser, "PORT", 3000), help="Port that the MCP server listens to in remote mode.")
    parser.add_argument("--mount-path",                                 type=str, default=os.getenv("MOUNT_PATH", "/mcp"), help="Path that the MCP server listens to in remote mode.")
    parser.add_argument("--https-cert-path",   "--https_cert_path",     type=str, default=os.getenv("HTTPS_CERT_PATH"), help="Path to the certificate (PEM) of the MCP server to serve HTTPS in remote mode. If not provided, the MCP server serves plain HTTP.")
    parser.add_argument("--https-key-path",    "--https_key_path",      type=str, default=os.getenv("HTTPS_KEY_PATH"),  help="Path to the private key (PEM) of the MCP server certificate (mandatory for HTTPS).")
    parser.add_argument("--https-key-password","--https_key_password",  type=str, default=os.getenv("HTTPS_KEY_PASSWORD"), help="Password to decrypt the private key of the MCP server certificate. Only needed if the key is password-protected.")
    
    # Logging-related arguments
    parser.add_argument("--log-level", "--log_level", type=str, default=os.getenv("LOG_LEVEL", "INFO"),
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Set the logging level (default: INFO)")
    
    # Trace-related arguments
    parser.add_argument("--traces-dir",    "--traces_dir",    type=str, default=os.getenv("TRACES_DIR"), help="Directory to store execution traces (optional). If not provided, traces will be stored in the 'traces' directory in the project root.")
    parser.add_argument("--trace-enable",  "--trace_enable",  type=str, default=os.getenv("TRACE_ENABLE", "False"), choices=["True", "False"], help="Enable trace storage. Default is False (trace storage disabled).")
    parser.add_argument("--trace-maxsize", "--trace_maxsize", type=int, default=_int_from_env(parser, "TRACE_MAXSIZE", 50), help="Maximum number of traces to store (default: 50)")

    # Tools refresh argument
    parser.add_argument("--tools-refresh-period", "--tools_refresh_period", type=int, default=_int_from_env(parser, "TOOLS_REFRESH_PERIOD", 300), help="Period in seconds of the background refresh of the tools (default: 300). 0 disables the refresh.")
    parser.add_argument("--tools-refresh-min-interval", "--tools_refresh_min_interval", type=int, default=_int_from_env(parser, "TOOLS_REFRESH_MIN_INTERVAL", 20), help="Minimum interval in seconds between consecutive refreshes of the tools triggered by list_tools or call_tool of an unknown tool. Set to 0 to refresh on every request, or -1 to disable on-demand refreshes (default: 20).")

    parser.add_argument(
        "--dedicated-runtimes", "--dedicated_runtimes",
        type=_dedicated_runtime_pair,
        nargs='+',
        default=[_dedicated_runtime_pair(item) for item in (os.getenv("DEDICATED_RUNTIMES") or "").split()],
        metavar="PATH=URL",
        help="Map specific ruleset paths to dedicated runtime servers. "
             "Provide one or more PATH=URL pairs (e.g. --dedicated-runtimes /myapp/1.0/myruleset/1.0=http://runtime2:9060/DecisionService). "
             "When call_tool is invoked, if the ruleset path starts with PATH the request is sent to URL instead of the default runtime."
    )

    args = parser.parse_args()

    # Re-parse with all defaults suppressed: only the options explicitly given on the command line remain
    for action in parser._actions:
        action.default = argparse.SUPPRESS
    args.explicit = vars(parser.parse_args())
    return args

def create_credentials(args):

    def create_credentials(args, auth_type, url):
        verifyssl = args.verifyssl != "False"
        verifyssl_hostname = args.verifyssl_hostname != "False"

        if (args.zenapikey and (auth_type is None or auth_type == "ZEN")):    # If zenapikey is provided, use it for authentication, unless another authentication type is specified
            return Credentials(
                odm_url=url,
                username=args.username,
                zenapikey=args.zenapikey,
                mtls_cert_path=args.mtls_cert_path, mtls_key_path=args.mtls_key_path, mtls_key_password=args.mtls_key_password,
                ssl_cert_path=args.ssl_cert_path,
                verify_ssl=verifyssl,
                verify_ssl_hostname=verifyssl_hostname,
            )
        elif (args.pkjwt_key_path and (auth_type is None or auth_type == "PKJWT")):  # OpenID PKJWT
            return Credentials(
                odm_url=url,
                token_url=args.token_url,
                scope=args.scope,
                client_id=args.client_id,
                pkjwt_cert_path=args.pkjwt_cert_path, pkjwt_key_path=args.pkjwt_key_path, pkjwt_key_password=args.pkjwt_key_password,
                mtls_cert_path=args.mtls_cert_path, mtls_key_path=args.mtls_key_path, mtls_key_password=args.mtls_key_password,
                ssl_cert_path=args.ssl_cert_path,
                verify_ssl=verifyssl,
                verify_ssl_hostname=verifyssl_hostname,
            )
        elif (args.client_id and (auth_type is None or auth_type == "SECRET")):  # OpenID without PKJWT - public (w/ secret) or private (w/o secret) OIDC App client
            return Credentials(
                odm_url=url,
                token_url=args.token_url,
                scope=args.scope,
                client_id=args.client_id,
                client_secret=args.client_secret,
                mtls_cert_path=args.mtls_cert_path, mtls_key_path=args.mtls_key_path, mtls_key_password=args.mtls_key_password,
                ssl_cert_path=args.ssl_cert_path,
                verify_ssl=verifyssl,
                verify_ssl_hostname=verifyssl_hostname,
            )
        elif (args.mtls_key_path and auth_type and auth_type == "NONE"):  # mTLS without authentication
            return Credentials(
                odm_url=url,
                mtls_cert_path=args.mtls_cert_path, mtls_key_path=args.mtls_key_path, mtls_key_password=args.mtls_key_password,
                ssl_cert_path=args.ssl_cert_path,
                verify_ssl=verifyssl,
                verify_ssl_hostname=verifyssl_hostname,
            )
        else:  # Default to basic authentication
            if not args.username or not args.password:
                raise ValueError("Username and password must be provided for basic authentication.")
            return Credentials(
                odm_url=url,
                username=args.username,
                password=args.password,
                mtls_cert_path=args.mtls_cert_path, mtls_key_path=args.mtls_key_path, mtls_key_password=args.mtls_key_password,
                ssl_cert_path=args.ssl_cert_path,
                verify_ssl=verifyssl,
                verify_ssl_hostname=verifyssl_hostname,
            )

    if args.runtime_url is not None:
        odm_url_runtime=args.runtime_url
    else:
        odm_url_runtime=args.url.rstrip('/')
        # replace 'res' with 'DecisionService'
        if odm_url_runtime.endswith('res'):
            odm_url_runtime=odm_url_runtime[:-3] + 'DecisionService'

    # Resolve a comma/semicolon-separated list of cert paths into a single file
    if args.ssl_cert_path:
        args.ssl_cert_path = merge_ssl_cert_paths(args.ssl_cert_path)

    console_credentials = create_credentials(args, args.console_auth_type, args.url)
    runtime_credentials = create_credentials(args, args.runtime_auth_type, odm_url_runtime)

    return console_credentials, runtime_credentials
    
class _SuppressAccessLogForProbes(logging.Filter):
    """Drop uvicorn access-log entries from health-check probes.

    Suppresses two categories:
    - Any request to the root path "/" (platform health-check) or "/healthcheck" (probes), regardless of source.
    - Requests whose client address matches the local pod IP or 127.0.0.1.

    Uvicorn emits: logger.info('%s - "%s %s HTTP/%s" %d', client_addr, method, path, http_version, status_code)
    so record.args is a 5-element tuple: (client_addr, method, path, http_version, status_code).
    """

    def __init__(self, local_ip: str) -> None:
        super().__init__()
        # Always include the loopback address in addition to the resolved pod IP.
        self._prefixes = {local_ip + ":", "127.0.0.1:"}

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "uvicorn.access":
            return True
        args = record.args
        if not (isinstance(args, tuple) and len(args) >= 3):
            return True
        # Suppress health-check hits on the root path, or on the /healthcheck path from any source.
        path = str(args[2]).split("?", 1)[0].rstrip("/")
        if path == "" or path.endswith("/healthcheck"):
            return False
        client = str(args[0])
        return not any(client.startswith(p) for p in self._prefixes)

def main():
    """Main entry point for the Decision MCP Server."""
    args = parse_arguments()
    
    # Configure logging with the specified level
    try:
        logging_level = getattr(logging, args.log_level)
    except AttributeError:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        logging.warning(f"Invalid log level '{args.log_level}' specified. Falling back to INFO.")
        logging_level = logging.INFO
    else:
        logging.basicConfig(
            level=logging_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    logging.info(f"Running Python {sys.version_info}. Logging level set to: {logging.getLevelName(logging_level)}")

    console_credentials, runtime_credentials = create_credentials(args)
    # Convert trace_enable from string to boolean
    trace_enable = args.trace_enable != "False"
    
    server = DecisionMCPServer(
        console_credentials=console_credentials,
        runtime_credentials=runtime_credentials,
        transport=args.transport, host=args.host, port=args.port, path=args.mount_path,
        traces_dir=args.traces_dir,
        trace_enable=trace_enable,
        trace_maxsize=args.trace_maxsize,
        tools_refresh_period=args.tools_refresh_period,
        tools_refresh_min_interval=args.tools_refresh_min_interval,
        dedicated_runtimes=args.dedicated_runtimes or None,
        https_cert_path    = args.https_cert_path,
        https_key_path     = args.https_key_path,
        https_key_password = args.https_key_password,
        startup_args       = getattr(args, "explicit", vars(args)),
    )

    # suppress access logs originating from probes when running in a k8s pod
    if server.is_running_in_pod():
        import uvicorn.config as _uvicorn_config
        probe_filter = _SuppressAccessLogForProbes(local_ip=socket.gethostbyname(socket.gethostname()))
        _original_configure_logging = _uvicorn_config.Config.configure_logging

        def _configure_logging_with_filter(self) -> None:  # type: ignore[override]
            _original_configure_logging(self)
            logging.getLogger("uvicorn.access").addFilter(probe_filter)

        _uvicorn_config.Config.configure_logging = _configure_logging_with_filter

    if args.verifyssl == "False":
        server.logger.warning("Verify SSL: False")

    server.start()
