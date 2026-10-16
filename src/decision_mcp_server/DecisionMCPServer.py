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

import json
from typing import Optional
from mcp.server.mcpserver.context import Context
from mcp_types import Tool, Resource, CallToolResult, TextContent
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import AnyUrl
import logging
import urllib3

from decision_mcp_server.DecisionServiceDescription import DecisionServiceDescription
from decision_mcp_server.Credentials import Credentials
from decision_mcp_server.DecisionServerManager import DecisionServerManager
from decision_mcp_server.config import INSTRUCTIONS, BASE_DIR
from decision_mcp_server.ExecutionToolTrace import ExecutionToolTrace, DiskTraceStorage
from decision_mcp_server.utils.ssl_utils import merge_ssl_cert_paths
import argparse
import os
import sys

class DecisionMCPServer:
    def __init__(self, console_credentials: Credentials, runtime_credentials: Credentials, 
                 transport: Optional[str] = 'stdio', host: Optional[str] = '0.0.0.0', port: Optional[int] = 3000, path: Optional[str] = '/mcp',
                 traces_dir: Optional[str] = None, trace_enable: bool = False, trace_maxsize: int = 50):
        # Get logger for this class
        self.logger = logging.getLogger(__name__)
        
        self.notes: dict[str, str] = {}
        self.repository: dict[str, DecisionServiceDescription] = {}
        
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

        self.transport = transport
        self.host      = host
        self.port      = port
        self.path      = path

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

    async def read_resource(self, uri: AnyUrl) -> str:
        if uri.scheme != "decisionservice":
            raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

        name = uri.path
        if name is not None:
            name = name.lstrip("/")
            return str(self.repository[name].__dict__)
        raise ValueError(f"DecisionService not found: {name}")

    async def list_tools(self) -> list[Tool]:
        self.logger.info("Listing ODM tools")
        # Ensure manager is initialized before using it
        if self.manager is None:
            self.manager = DecisionServerManager(console_credentials=self.console_credentials, 
                                                 runtime_credentials=self.runtime_credentials)
            
        rulesets = self.manager.fetch_rulesets()
        extractedTools = self.manager.generate_tools_format(rulesets)
        tools = []
        for decisionService in extractedTools:   
            tool_info = decisionService.tool_description
            tools.append(tool_info)
            self.repository[decisionService.tool_name] = decisionService
        return tools

    async def call_tool(self, name: str, arguments: dict | None, context: Context) -> CallToolResult:
        if self.repository.get(name) is None:
            self.logger.error("Tool not found: %s", name)
            raise ToolError(f"Unknown tool: {name}")

        self.logger.info("Invoking decision service for tool: %s with arguments: %s", name, arguments)
        # Ensure manager is initialized before using it
        if self.manager is None:
            self.manager = DecisionServerManager(console_credentials=self.console_credentials, 
                                                 runtime_credentials=self.runtime_credentials)

        try:
            result = self.manager.invokeDecisionService(
                rulesetPath=self.repository[name].rulesetPath,
                decisionInputs=arguments
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

    def start(self):

        self.manager = DecisionServerManager(console_credentials=self.console_credentials, 
                                             runtime_credentials=self.runtime_credentials)

        self.server = MCPServer(name="ibm-odm-decision-mcp-server",
                              instructions=INSTRUCTIONS,
                             )

        # Register handlers
        self.server.read_resource  = self.read_resource
        self.server.list_resources = self.list_resources
        self.server.list_tools = self.list_tools
        self.server.call_tool  = self.call_tool

                        # sse_path=self.path,
                        # stateless_http=True,
        self.server.run(transport=self.transport,
                        host=self.host,
                        port=self.port,
                        streamable_http_path=self.path,
        )

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
    parser.add_argument("--port",                                       type=int, default=os.getenv("PORT", 3000), help="Port that the MCP server listens to in remote mode.")
    parser.add_argument("--mount-path",                                 type=str, default=os.getenv("MOUNT_PATH", "/mcp"), help="Path that the MCP server listens to in remote mode.")
    
    # Logging-related arguments
    parser.add_argument("--log-level", "--log_level", type=str, default=os.getenv("LOG_LEVEL", "INFO"),
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Set the logging level (default: INFO)")
    
    # Trace-related arguments
    parser.add_argument("--traces-dir",    "--traces_dir",    type=str, default=os.getenv("TRACES_DIR"), help="Directory to store execution traces (optional). If not provided, traces will be stored in the 'traces' directory in the project root.")
    parser.add_argument("--trace-enable",  "--trace_enable",  type=str, default=os.getenv("TRACE_ENABLE", "False"), choices=["True", "False"], help="Enable trace storage. Default is False (trace storage disabled).")
    parser.add_argument("--trace-maxsize", "--trace_maxsize", type=int, default=int(os.getenv("TRACE_MAXSIZE", "50")), help="Maximum number of traces to store (default: 50)")

    return parser.parse_args()

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
        elif (args.client_secret and (auth_type is None or auth_type == "SECRET")):  # OpenID Client Secret provided
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
    )
    server.start()
