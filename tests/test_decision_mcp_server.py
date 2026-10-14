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

import pytest
from unittest.mock import Mock, patch
import os
import argparse
from decision_mcp_server.DecisionMCPServer import DecisionMCPServer, parse_arguments, create_credentials
from decision_mcp_server.Credentials import Credentials
from decision_mcp_server.config import INSTRUCTIONS
from mcp_types import CallToolResult
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
import json

# Test fixtures
@pytest.fixture
def mock_console_credentials():
    return Credentials(
        odm_url="http://test:9060/res",
        username="test_user",
        password="test_pass"
    )

@pytest.fixture
def mock_runtime_credentials():
    return Credentials(
        odm_url="http://test:9060/DecisionService",
        username="test_user",
        password="test_pass"
    )

@pytest.fixture
def mock_server():
    return Mock(spec=MCPServer)

@pytest.fixture
def decision_server(mock_console_credentials, mock_runtime_credentials, mock_server):
    server = DecisionMCPServer(console_credentials=mock_console_credentials, runtime_credentials=mock_runtime_credentials)
    server.server = mock_server
    server.manager = Mock()
    return server

# Test DecisionMCPServer initialization
def test_server_initialization(decision_server):
    assert isinstance(decision_server.notes, dict)
    assert isinstance(decision_server.repository, dict)
    assert decision_server.server is not None
    assert decision_server.console_credentials is not None
    assert decision_server.runtime_credentials is not None

def test_server_init_disables_urllib3_warnings():
    """urllib3.disable_warnings() must be called (no args) during DecisionMCPServer.__init__."""
    with patch('urllib3.disable_warnings') as mock_disable_warnings:
        credentials = Credentials(
            odm_url="http://test:9060/res",
            username="user",
            password="pass"
        )
        DecisionMCPServer(
            console_credentials=credentials,
            runtime_credentials=credentials
        )
        mock_disable_warnings.assert_called_once_with()

# Test argument parsing
@pytest.mark.parametrize("args,expected", [
    (
        ["--url", "http://test-odm:9060/res"],
        {"url": "http://test-odm:9060/res"}
    ),
    (
        ["--runtime-url", "http://test-odm:9060/DecisionService"],
        {"runtime_url": "http://test-odm:9060/DecisionService"}
    ),
    (
        ["--username", "testuser", "--password", "testpass"],
        {"username": "testuser", "password": "testpass"}
    ),
    (
        ["--zenapikey", "test-key"],
        {"zenapikey": "test-key"}
    ),
    (
        ["--client-id", "test-client", "--client-secret", "test-secret", "--token-url", "http://op/token", "--scope", "openid"],
        {"client_id": "test-client", "client_secret": "test-secret", "token_url": "http://op/token", "scope": "openid"}
    ),
    (
        ["--pkjwt-cert-path", "/custom/cert/file", "--pkjwt-key-path", "/custom/key/file", "--pkjwt-key-password", "xyz-password"],
        {"pkjwt_cert_path": "/custom/cert/file", "pkjwt_key_path": "/custom/key/file", "pkjwt_key_password": "xyz-password"}
    ),
    (
        ["--mtls-cert-path", "/custom/cert/file", "--mtls-key-path", "/custom/key/file", "--mtls-key-password", "xyz-password"],
        {"mtls_cert_path": "/custom/cert/file", "mtls_key_path": "/custom/key/file", "mtls_key_password": "xyz-password"}
    ),
    (
        ["--verifyssl", "False"],
        {"verifyssl": "False"}
    ),
    (
        ["--ssl-cert-path", "/custom/cert/file"],
        {"ssl_cert_path": "/custom/cert/file"}
    ),
    (
        ["--console-auth-type", "PKJWT", "--runtime-auth-type", "BASIC"],
        {"console_auth_type": "PKJWT", "runtime_auth_type": "BASIC"}
    ),
    (
        ["--traces-dir", "/custom/traces/dir"],
        {"traces_dir": "/custom/traces/dir"}
    ),
    (
        ["--trace-enable", "True"],
        {"trace_enable": "True"}  # Explicitly enabled
    ),
    (
        ["--trace-enable", "False"],
        {"trace_enable": "False"}  # Explicitly disabled
    ),
    (
        ["--trace-maxsize", "100"],
        {"trace_maxsize": 100}
    ),
    (
        ["--log-level", "DEBUG"],
        {"log_level": "DEBUG"}  # Test log level argument
    ),
    (
        ["--transport", "streamable-http", "--host", "127.0.0.1", "--port", "3001", "--mount-path", "/decision-mcp"],
        {"transport": "streamable-http", "host": "127.0.0.1", "port": 3001, "mount_path": "/decision-mcp"}  # Test remote arguments
    ),
    (
        ["--transport", "streamable-http"],
        {"transport": "streamable-http", "host": "0.0.0.0", "port": 3000, "mount_path": "/mcp"}  # Test remote arguments with default values
    ),
    (
        [],  # No arguments
        {"scope": "openid", "verifyssl": "True", "trace_enable": "False", "trace_maxsize": 50, "log_level": "INFO", "transport":"stdio"}  # Default values
    ),
])
def test_parse_arguments(args, expected):  # Added 'expected' parameter
    with patch('sys.argv', ['script'] + args):
        parsed_args = parse_arguments()
        for key, value in expected.items():
            assert getattr(parsed_args, key) == value

# Test credentials creation
def test_create_credentials_basic_auth():
    args = argparse.Namespace(
        url="http://test:9060/res",
        odm_url="http://test:9060/res",
        runtime_url=None,
        username="test_user",
        password="test_pass",
        zenapikey=None,
        client_id=None,
        client_secret=None,
        token_url=None,
        scope="openid",
        verifyssl="True",
        verifyssl_hostname="True",
        ssl_cert_path=None,
        pkjwt_cert_path=None,
        pkjwt_key_path=None,
        pkjwt_key_password=None,
        mtls_cert_path=None,
        mtls_key_path=None,
        mtls_key_password=None,
        console_auth_type=None,
        runtime_auth_type=None,
        traces_dir=None,
        trace_enable="False",
        trace_maxsize=50,
        log_level="INFO"
    )
    console_credentials, runtime_credentials = create_credentials(args)
    assert console_credentials.odm_url == "http://test:9060/res"
    assert console_credentials.username == "test_user"
    assert console_credentials.password == "test_pass"

    assert runtime_credentials.odm_url == "http://test:9060/DecisionService"
    assert runtime_credentials.username == "test_user"
    assert runtime_credentials.password == "test_pass"

def test_create_credentials_zen_api():
    args = argparse.Namespace(
        url="http://test:9060/res",
        runtime_url="http://test:9060/DecisionService",
        username="test_user",
        password=None,
        zenapikey="test-key",
        client_id=None,
        client_secret=None,
        token_url=None,
        scope="openid",
        verifyssl="True",
        verifyssl_hostname="True",
        ssl_cert_path=None,
        pkjwt_cert_path=None,
        pkjwt_key_path=None,
        pkjwt_key_password=None,
        mtls_cert_path=None,
        mtls_key_path=None,
        mtls_key_password=None,
        console_auth_type=None,
        runtime_auth_type=None,
        traces_dir=None,
        trace_enable="False",
        trace_maxsize=50,
        log_level="INFO"
    )
    console_credentials, runtime_credentials = create_credentials(args)
    assert console_credentials.zenapikey == "test-key"
    assert runtime_credentials.zenapikey == "test-key"

def test_create_credentials_openid():
    args = argparse.Namespace(
        url="http://test:9060/res",
        runtime_url="http://test:9060/DecisionService",
        username=None,
        password=None,
        zenapikey=None,
        client_id="test-client",
        client_secret="test-secret",
        token_url="http://op/token",
        scope="openid",
        verifyssl="True",
        verifyssl_hostname="True",
        ssl_cert_path=None,
        pkjwt_cert_path=None,
        pkjwt_key_path=None,
        pkjwt_key_password=None,
        mtls_cert_path=None,
        mtls_key_path=None,
        mtls_key_password=None,
        console_auth_type=None,
        runtime_auth_type=None,
        traces_dir=None,
        trace_enable="False",
        trace_maxsize=50,
        log_level="INFO"
    )
    console_credentials, runtime_credentials = create_credentials(args)
    assert console_credentials.client_id == "test-client"
    assert console_credentials.client_secret == "test-secret"
    assert console_credentials.token_url == "http://op/token"
    assert console_credentials.scope == "openid"

    assert runtime_credentials.client_id == "test-client"
    assert runtime_credentials.client_secret == "test-secret"
    assert runtime_credentials.token_url == "http://op/token"
    assert runtime_credentials.scope == "openid"

# Test error cases
def test_create_credentials_missing_basic_auth():
    args = argparse.Namespace(
        url="http://test:9060/res",
        odm_url="http://test:9060/res",
        runtime_url=None,
        username="username",
        password=None,
        zenapikey=None,
        client_id=None,
        client_secret=None,
        token_url=None,
        scope="openid",
        verifyssl="True",
        verifyssl_hostname="True",
        ssl_cert_path=None,
        pkjwt_cert_path=None,
        pkjwt_key_path=None,
        pkjwt_key_password=None,
        mtls_cert_path=None,
        mtls_key_path=None,
        mtls_key_password=None,
        console_auth_type=None,
        runtime_auth_type=None,
        traces_dir=None,
        trace_enable="False",
        trace_maxsize=50,
        log_level="INFO"
    )
    with pytest.raises(ValueError) as exc_info:
        create_credentials(args)
    assert str(exc_info.value) == "Username and password must be provided for basic authentication."

# Test SSL verification
@pytest.mark.parametrize("verify_ssl,expected", [
    ("True", True),
    ("False", False)
])
def test_ssl_verification(verify_ssl, expected):
    args = argparse.Namespace(
        url="http://test:9060/res",
        odm_url="http://test:9060/res",
        runtime_url=None,
        username="test_user",
        password="test_pass",
        zenapikey=None,
        client_id=None,
        client_secret=None,
        token_url=None,
        scope="openid",
        verifyssl=verify_ssl,
        verifyssl_hostname="True",
        ssl_cert_path=None,
        pkjwt_cert_path=None,
        pkjwt_key_path=None,
        pkjwt_key_password=None,
        mtls_cert_path=None,
        mtls_key_path=None,
        mtls_key_password=None,
        console_auth_type=None,
        runtime_auth_type=None,
        traces_dir=None,
        trace_enable="False",
        trace_maxsize=50,
        log_level="INFO"
    )
    console_credentials, runtime_credentials = create_credentials(args)
    assert console_credentials.verify_ssl == expected
    assert runtime_credentials.verify_ssl == expected

# Test environment variables
def test_environment_variables():
    with patch.dict(os.environ, {
        'ODM_URL': 'http://env-test:9060/res',
        'ODM_USERNAME': 'env_user',
        'ODM_PASSWORD': 'env_pass',
        'TRACES_DIR': '/env/traces/dir',
        'TRACE_ENABLE': 'True',  # Testing explicit enable since default is now False
        'TRACE_MAXSIZE': '200',
        'LOG_LEVEL': 'DEBUG'
    }), patch('sys.argv', ['script']):  # Added sys.argv patch
        args = parse_arguments()
        assert args.url == 'http://env-test:9060/res'
        assert args.username == 'env_user'
        assert args.password == 'env_pass'
        assert args.traces_dir == '/env/traces/dir'
        assert args.trace_enable == "True"  # Should be "True" string because we set it explicitly
        assert args.trace_maxsize == 200
        assert args.log_level == 'DEBUG'

class DummyTool:
    def __init__(self, name, description, input_schema):
        self.name = name
        self.description = description
        self.input_schema = input_schema

# Mock the types module
@pytest.fixture
def mock_types():
    mock = Mock()
    mock.Tool = DummyTool
    return mock

@pytest.fixture
def mock_manager():
    manager = Mock()
    # Setup mock rulesets
    manager.fetch_rulesets.return_value = [
        {"id": "rule1", "description": "First ruleset"},
        {"id": "rule2", "description": "Second ruleset"}
    ]
    # Setup mock tools
    manager.generate_tools_format.return_value = [
        Mock(
            tool_name="tool1",
            tool_description=DummyTool(
                name="tool1",
                description="First tool",
                input_schema={"type": "object"}
            )
        ),
        Mock(
            tool_name="tool2",
            tool_description=DummyTool(
                name="tool2",
                description="Second tool",
                input_schema={"type": "object"}
            )
        )
    ]
    return manager

@pytest.fixture
def server(mock_manager):
    credentials = Credentials(
        odm_url="http://test:9060/res",
        username="test",
        password="test"
    )
    server = DecisionMCPServer(console_credentials=credentials, runtime_credentials=credentials, traces_dir=None, trace_enable=True, trace_maxsize=50)  # Explicitly enable traces for testing
    server.manager = mock_manager
    return server

@pytest.mark.asyncio
async def test_list_tools(server, mock_manager):
    # Execute
    tools = await server.list_tools()

    # Verify
    assert len(tools) == 2
    assert mock_manager.fetch_rulesets.called
    assert mock_manager.generate_tools_format.called
    
    # Verify tool properties
    assert tools[0].name == "tool1"
    assert tools[1].name == "tool2"
    
    # Verify repository updates
    assert len(server.repository) == 2
    assert "tool1" in server.repository
    assert "tool2" in server.repository

@pytest.mark.asyncio
async def test_list_tools_empty(server, mock_manager):
    # Setup empty response
    mock_manager.fetch_rulesets.return_value = []
    mock_manager.generate_tools_format.return_value = []

    # Execute
    tools = await server.list_tools()

    # Verify
    assert len(tools) == 0
    assert len(server.repository) == 0

@pytest.mark.asyncio
async def test_list_tools_error_handling(server, mock_manager):
    # Setup error condition
    mock_manager.fetch_rulesets.side_effect = Exception("Failed to fetch rulesets")

    # Verify error is propagated
    with pytest.raises(Exception) as exc_info:
        await server.list_tools()
    assert str(exc_info.value) == "Failed to fetch rulesets"

@pytest.mark.asyncio
async def test_call_tool_success(server, mock_manager):
    # Setup mock response
    mock_manager.invokeDecisionService.return_value = {
        "result": "decision_result",
        "__DecisionID__": "123"  # This should be removed in response
    }

    # Setup test data
    tool_name = "tool1"
    arguments = {"input": "test_value"}
    
    # Add tool to repository
    server.repository[tool_name] = Mock(rulesetPath="/test/path")

    # Execute
    result = await server.call_tool(tool_name, arguments, {})

    # Verify
    assert mock_manager.invokeDecisionService.called
    assert mock_manager.invokeDecisionService.call_args[1] == {
        "rulesetPath": "/test/path",
        "decisionInputs": arguments
    }
    
    # Verify response format
    assert len(result.content) == 1
    assert isinstance(result, CallToolResult)
    assert result.content[0].type == "text"
    
    # Verify response content
    response_data = json.loads(result.content[0].text)
    assert response_data["result"] == "decision_result"
    assert "__DecisionID__" not in response_data

@pytest.mark.asyncio
async def test_call_tool_unknown_tool(server):
    # Try to call non-existent tool
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool("unknown_tool", {}, {})
    assert str(exc_info.value) == "Unknown tool: unknown_tool"

@pytest.mark.asyncio
async def test_call_tool_error_handling(server, mock_manager):
    # Setup
    tool_name = "tool1"
    server.repository[tool_name] = Mock(rulesetPath="/test/path")
    mock_manager.invokeDecisionService.side_effect = ToolError("Decision service error")

    # Verify error is propagated
    with pytest.raises(ToolError) as exc_info:
        await server.call_tool(tool_name, {}, {})
    assert str(exc_info.value) == "Decision service error"

@pytest.mark.asyncio
async def test_call_tool_non_dict_response(server, mock_manager):
    # Setup mock response as string
    mock_manager.invokeDecisionService.return_value = "string_response"
    tool_name = "tool1"
    server.repository[tool_name] = Mock(rulesetPath="/test/path")

    # Execute
    result = await server.call_tool(tool_name, {}, {})

    # Verify string handling
    assert len(result.content) == 1
    assert isinstance(result, CallToolResult)
    assert result.content[0].text == "string_response"

# Test trace functionality with new parameters
@pytest.fixture
def server_with_traces_enabled():
    credentials = Credentials(
        odm_url="http://test:9060/res",
        username="test",
        password="test"
    )
    # Explicitly enable traces for testing
    server = DecisionMCPServer(console_credentials=credentials, runtime_credentials=credentials, traces_dir=None, trace_enable=True, trace_maxsize=10)
    server.manager = Mock()
    return server

@pytest.fixture
def server_with_traces_disabled():
    credentials = Credentials(
        odm_url="http://test:9060/res",
        username="test",
        password="test"
    )
    # Default behavior is traces disabled, but we're explicit here for clarity in tests
    server = DecisionMCPServer(console_credentials=credentials, runtime_credentials=credentials, traces_dir=None, trace_enable=False, trace_maxsize=10)
    server.manager = Mock()
    return server

@pytest.mark.asyncio
async def test_call_tool_with_traces_enabled(server_with_traces_enabled):
    # Setup mock response
    server_with_traces_enabled.manager.invokeDecisionService.return_value = {
        "result": "decision_result",
        "__DecisionID__": "123"
    }
    
    # Setup test data
    tool_name = "tool1"
    arguments = {"input": "test_value"}
    
    # Add tool to repository
    server_with_traces_enabled.repository[tool_name] = Mock(rulesetPath="/test/path")
    server_with_traces_enabled.manager.fetch_rulesets.return_value = {}

    # Execute
    result = await server_with_traces_enabled.call_tool(tool_name, arguments, {})
    
    # Verify trace storage was used
    assert server_with_traces_enabled.execution_traces is not None
    
    # Verify response
    assert len(result.content) == 1
    assert result.content[0].type == "text"

@pytest.mark.asyncio
async def test_call_tool_with_traces_disabled(server_with_traces_disabled):
    # Setup mock response
    server_with_traces_disabled.manager.invokeDecisionService.return_value = {
        "result": "decision_result",
        "__DecisionID__": "123"
    }
    
    # Setup test data
    tool_name = "tool1"
    arguments = {"input": "test_value"}
    
    # Add tool to repository
    server_with_traces_disabled.repository[tool_name] = Mock(rulesetPath="/test/path")
    server_with_traces_disabled.manager.fetch_rulesets.return_value = {}

    # Execute
    result = await server_with_traces_disabled.call_tool(tool_name, arguments, {})
    
    # Verify trace storage was not used
    assert server_with_traces_disabled.execution_traces is None
    
    # Verify response
    assert len(result.content) == 1
    assert result.content[0].type == "text"

@pytest.mark.asyncio
async def test_list_execution_traces_with_traces_disabled(server_with_traces_disabled):
    # Execute
    traces = await server_with_traces_disabled.list_execution_traces()
    
    # Verify empty list is returned when traces are disabled
    assert len(traces) == 0

@pytest.mark.asyncio
async def test_get_execution_trace_with_traces_disabled(server_with_traces_disabled):
    # Execute
    trace = await server_with_traces_disabled.get_execution_trace("any_id")
    
    # Verify None is returned when traces are disabled
    assert trace is None

# Test transport configuration
def test_server_initialization_with_streamable_http_transport():
    """Test DecisionMCPServer initialization with streamable-http transport."""
    credentials = Credentials(
        odm_url="http://test:9060/res",
        username="test",
        password="test"
    )
    
    # Create server with streamable-http transport
    server = DecisionMCPServer(
        console_credentials=credentials,
        runtime_credentials=credentials,
        transport="streamable-http",
        host="127.0.0.1",
        port=3001,
        path="/decision-mcp"
    )
    
    # Verify transport configuration
    assert server.transport == "streamable-http"
    assert server.host == "127.0.0.1"
    assert server.port == 3001
    assert server.path == "/decision-mcp"

def test_server_initialization_with_default_transport():
    """Test DecisionMCPServer initialization with default stdio transport."""
    credentials = Credentials(
        odm_url="http://test:9060/res",
        username="test",
        password="test"
    )
    
    # Create server with default transport
    server = DecisionMCPServer(
        console_credentials=credentials,
        runtime_credentials=credentials
    )
    
    # Verify default transport configuration
    assert server.transport == "stdio"
    assert server.host == "0.0.0.0"
    assert server.port == 3000
    assert server.path == "/mcp"

def test_server_start_with_streamable_http_transport():
    """Test that server.start() correctly configures SDK_MCPServer with streamable-http transport."""
    credentials = Credentials(
        odm_url="http://test:9060/res",
        username="test",
        password="test"
    )
    
    # Create server with streamable-http transport
    server = DecisionMCPServer(
        console_credentials=credentials,
        runtime_credentials=credentials,
        transport="streamable-http",
        host="127.0.0.1",
        port=3001,
        path="/custom-path"
    )
    
    # Mock the SDK_MCPServer and its run method
    with patch('decision_mcp_server.DecisionMCPServer.MCPServer') as mock_fastmcp_class, \
         patch('decision_mcp_server.DecisionMCPServer.DecisionServerManager') as mock_manager_class:
        
        # Setup mocks
        mock_fastmcp = mock_fastmcp_class.return_value
        mock_fastmcp._mcp_server = Mock()
        mock_fastmcp._mcp_server.list_resources = Mock()
        mock_fastmcp._mcp_server.read_resource = Mock()
        mock_fastmcp._mcp_server.list_tools = Mock()
        mock_fastmcp._mcp_server.call_tool = Mock()
        mock_fastmcp.run = Mock()
        
        mock_manager = mock_manager_class.return_value
        
        # Call start
        server.start()
        
        # Verify SDK_MCPServer was initialized with correct parameters
        mock_fastmcp_class.assert_called_once_with(
            name="ibm-odm-decision-mcp-server",
            instructions=INSTRUCTIONS,
        )
        
        # Verify run was called with streamable-http transport
        mock_fastmcp.run.assert_called_once_with(
            transport="streamable-http",
            host="127.0.0.1",
            port=3001,
            streamable_http_path="/custom-path"
        )
        
        # Verify manager was initialized
        assert server.manager is not None

def test_server_start_with_sse_transport():
    """Test that server.start() correctly configures SDK_MCPServer with sse transport."""
    credentials = Credentials(
        odm_url="http://test:9060/res",
        username="test",
        password="test"
    )
    
    # Create server with sse transport
    server = DecisionMCPServer(
        console_credentials=credentials,
        runtime_credentials=credentials,
        transport="sse",
        host="0.0.0.0",
        port=8080,
        path="/sse-endpoint"
    )
    
    # Mock the SDK_MCPServer and its run method
    with patch('decision_mcp_server.DecisionMCPServer.MCPServer') as mock_fastmcp_class, \
         patch('decision_mcp_server.DecisionMCPServer.DecisionServerManager') as mock_manager_class:
        
        # Setup mocks
        mock_fastmcp = mock_fastmcp_class.return_value
        mock_fastmcp._mcp_server = Mock()
        mock_fastmcp._mcp_server.list_resources = Mock()
        mock_fastmcp._mcp_server.read_resource = Mock()
        mock_fastmcp._mcp_server.list_tools = Mock()
        mock_fastmcp._mcp_server.call_tool = Mock()
        mock_fastmcp.run = Mock()
        
        mock_manager = mock_manager_class.return_value
        
        # Call start
        server.start()
        
        # Verify SDK_MCPServer was initialized with correct parameters
            # sse_path="/sse-endpoint",
        mock_fastmcp_class.assert_called_once_with(
            name="ibm-odm-decision-mcp-server",
            instructions=INSTRUCTIONS,
        )
        
        # Verify run was called with sse transport
        mock_fastmcp.run.assert_called_once_with(
            transport="sse",
            host="0.0.0.0",
            port=8080,
            streamable_http_path="/sse-endpoint"
        )


# ── Automatic tool update tests ────────────────────────────────────────────────
# These tests cover the update_tool / get_decisionServices feature that
# automatically promotes a tool to the currently highest ruleset version
# whenever call_tool is invoked.

def _make_server():
    """Return a DecisionMCPServer with a mocked manager."""
    credentials = Credentials(odm_url="http://test:9060/res", username="test", password="test")
    server = DecisionMCPServer(
        console_credentials=credentials,
        runtime_credentials=credentials,
        traces_dir=None,
        trace_enable=False,
        trace_maxsize=10,
    )
    server.manager = Mock()
    return server


def _make_decision_service(ruleset_id, version, input_schema=None):
    """Build a minimal DecisionServiceDescription-like Mock."""
    if input_schema is None:
        input_schema = {"type": "object", "properties": {"input": {"type": "string"}}}
    ruleset = {
        "id": ruleset_id,
        "version": version,
        "displayName": "Test Ruleset",
        "description": "Test",
        "properties": [
            {"id": "ruleset.status", "value": "enabled"},
            {"id": "agent.enabled", "value": "true"},
        ],
    }
    from mcp_types import Tool
    ds = Mock()
    ds.ruleset = ruleset
    ds.rulesetPath = "/" + ruleset_id
    ds.tool_name = "my_tool"
    ds.tool_description = Tool(name="my_tool", description="Test", inputSchema=input_schema)
    return ds


# ── get_decisionServices ───────────────────────────────────────────────────────

def test_get_decisionServices_no_ruleset_returns_all_tools(server, mock_manager):
    """When no ruleset filter is given (list_tools path) all formatted tools are returned."""
    mock_manager.fetch_rulesets.return_value = {"app/rs": {"id": "app/1.0/rs"}}
    mock_manager.generate_tools_format.return_value = [Mock(tool_name="tool1")]

    result = server.get_decisionServices()

    mock_manager.fetch_rulesets.assert_called_once_with(None)
    mock_manager.generate_tools_format.assert_called_once()
    assert len(result) == 1


def test_get_decisionServices_higher_version_found():
    """A higher-version ruleset is detected and its DecisionServiceDescription returned."""
    server = _make_server()
    current_ruleset = {"id": "app/1.0/rs", "version": "1.0"}
    higher_ruleset  = {"id": "app/2.0/rs", "version": "2.0"}
    rulesets_response = {"app/rs": higher_ruleset}

    server.manager.fetch_rulesets.return_value = rulesets_response
    server.manager.ruleset_key.return_value = "app/rs"
    new_ds = Mock(tool_name="my_tool")
    server.manager.generate_tools_format.return_value = [new_ds]

    result = server.get_decisionServices(current_ruleset)

    # generate_tools_format must receive only the higher-version ruleset
    server.manager.generate_tools_format.assert_called_once_with({"app/rs": higher_ruleset})
    assert result == [new_ds]


def test_get_decisionServices_same_version_no_update():
    """When the server still returns the same ruleset id, no update is needed."""
    server = _make_server()
    current_ruleset = {"id": "app/1.0/rs", "version": "1.0"}
    rulesets_response = {"app/rs": current_ruleset}   # same id → no higher version

    server.manager.fetch_rulesets.return_value = rulesets_response
    server.manager.ruleset_key.return_value = "app/rs"
    server.manager.generate_tools_format.return_value = []

    result = server.get_decisionServices(current_ruleset)

    # generate_tools_format must be called with empty dict (nothing to update)
    server.manager.generate_tools_format.assert_called_once_with({})
    assert result == []


def test_get_decisionServices_ruleset_removed_from_server():
    """When the ruleset no longer exists on the server, no update is performed."""
    server = _make_server()
    current_ruleset = {"id": "app/1.0/rs", "version": "1.0"}
    rulesets_response = {}   # ruleset has been deleted

    server.manager.fetch_rulesets.return_value = rulesets_response
    server.manager.ruleset_key.return_value = "app/rs"
    server.manager.generate_tools_format.return_value = []

    result = server.get_decisionServices(current_ruleset)

    server.manager.generate_tools_format.assert_called_once_with({})
    assert result == []


def test_get_decisionServices_fetch_failure_returns_empty():
    """If fetch_rulesets raises while checking a specific ruleset, the exception is
    silently absorbed and an empty list is returned (keep using the current ruleset)."""
    server = _make_server()
    current_ruleset = {"id": "app/1.0/rs", "version": "1.0"}

    server.manager.fetch_rulesets.side_effect = Exception("RES console unreachable")
    server.manager.generate_tools_format.return_value = []

    result = server.get_decisionServices(current_ruleset)

    # generate_tools_format must be called with empty dict (fallback)
    server.manager.generate_tools_format.assert_called_once_with({})
    assert result == []


def test_get_decisionServices_fetch_failure_with_no_ruleset_propagates():
    """If fetch_rulesets raises during list_tools (no ruleset filter), the exception
    must propagate so the caller knows the server is unreachable."""
    server = _make_server()

    server.manager.fetch_rulesets.side_effect = Exception("RES console unreachable")

    with pytest.raises(Exception, match="RES console unreachable"):
        server.get_decisionServices()


# ── update_tool ────────────────────────────────────────────────────────────────

def test_update_tool_promotes_compatible_higher_version():
    """When a higher version with the same input schema is found, the repository
    entry must be replaced with the new DecisionServiceDescription."""
    server = _make_server()
    schema = {"type": "object", "properties": {"loan": {"type": "number"}}}

    old_ds = _make_decision_service("app/1.0/rs", "1.0", schema)
    server.repository["my_tool"] = old_ds

    new_ds = _make_decision_service("app/2.0/rs", "2.0", schema)
    server.manager.fetch_rulesets.return_value = {"app/rs": new_ds.ruleset}
    server.manager.ruleset_key.return_value = "app/rs"
    server.manager.generate_tools_format.return_value = [new_ds]

    server.update_tool("my_tool")

    assert server.repository["my_tool"] is new_ds
    assert server.repository["my_tool"].rulesetPath == "/app/2.0/rs"


def test_update_tool_does_not_promote_incompatible_schema():
    """When the higher version has a different input schema, the tool must NOT be
    updated — the MCP client would be sending inputs the new version doesn't expect."""
    server = _make_server()
    old_schema = {"type": "object", "properties": {"amount": {"type": "number"}}}
    new_schema  = {"type": "object", "properties": {"loanAmount": {"type": "number"}}}

    old_ds = _make_decision_service("app/1.0/rs", "1.0", old_schema)
    server.repository["my_tool"] = old_ds

    new_ds = _make_decision_service("app/2.0/rs", "2.0", new_schema)
    server.manager.fetch_rulesets.return_value = {"app/rs": new_ds.ruleset}
    server.manager.ruleset_key.return_value = "app/rs"
    server.manager.generate_tools_format.return_value = [new_ds]

    server.update_tool("my_tool")

    # Repository must still point to the old version
    assert server.repository["my_tool"] is old_ds


def test_update_tool_no_higher_version_leaves_repository_unchanged():
    """When no higher version is available, the repository entry stays the same."""
    server = _make_server()
    schema = {"type": "object"}
    current_ds = _make_decision_service("app/1.0/rs", "1.0", schema)
    server.repository["my_tool"] = current_ds

    # fetch_rulesets returns same id → get_decisionServices returns []
    server.manager.fetch_rulesets.return_value = {"app/rs": current_ds.ruleset}
    server.manager.ruleset_key.return_value = "app/rs"
    server.manager.generate_tools_format.return_value = []

    server.update_tool("my_tool")

    assert server.repository["my_tool"] is current_ds


# ── call_tool integration with update_tool ────────────────────────────────────

@pytest.mark.asyncio
async def test_call_tool_uses_updated_ruleset_path():
    """call_tool must invoke the decision service using the promoted ruleset path
    when update_tool finds a compatible higher version."""
    server = _make_server()
    schema = {"type": "object"}

    old_ds = _make_decision_service("app/1.0/rs", "1.0", schema)
    server.repository["my_tool"] = old_ds

    new_ds = _make_decision_service("app/2.0/rs", "2.0", schema)
    server.manager.fetch_rulesets.return_value = {"app/rs": new_ds.ruleset}
    server.manager.ruleset_key.return_value = "app/rs"
    server.manager.generate_tools_format.return_value = [new_ds]
    server.manager.invokeDecisionService.return_value = {"result": "ok"}

    result = await server.call_tool("my_tool", {"input": "x"}, {})

    # The invocation must use the new (promoted) path
    server.manager.invokeDecisionService.assert_called_once_with(
        rulesetPath="/app/2.0/rs",
        decisionInputs={"input": "x"},
    )
    assert result.is_error is False


@pytest.mark.asyncio
async def test_call_tool_keeps_original_ruleset_when_no_update():
    """call_tool must invoke the decision service using the original ruleset path
    when no higher version is available."""
    server = _make_server()
    schema = {"type": "object"}

    current_ds = _make_decision_service("app/1.0/rs", "1.0", schema)
    server.repository["my_tool"] = current_ds

    # No higher version
    server.manager.fetch_rulesets.return_value = {"app/rs": current_ds.ruleset}
    server.manager.ruleset_key.return_value = "app/rs"
    server.manager.generate_tools_format.return_value = []
    server.manager.invokeDecisionService.return_value = {"result": "ok"}

    await server.call_tool("my_tool", {}, {})

    server.manager.invokeDecisionService.assert_called_once_with(
        rulesetPath="/app/1.0/rs",
        decisionInputs={},
    )


@pytest.mark.asyncio
async def test_call_tool_keeps_original_ruleset_when_fetch_fails():
    """If the RES console is unreachable during update_tool, call_tool must fall back
    gracefully and still invoke the original ruleset path."""
    server = _make_server()
    schema = {"type": "object"}

    current_ds = _make_decision_service("app/1.0/rs", "1.0", schema)
    server.repository["my_tool"] = current_ds

    server.manager.fetch_rulesets.side_effect = Exception("timeout")
    server.manager.generate_tools_format.return_value = []
    server.manager.invokeDecisionService.return_value = {"result": "ok"}

    await server.call_tool("my_tool", {}, {})

    server.manager.invokeDecisionService.assert_called_once_with(
        rulesetPath="/app/1.0/rs",
        decisionInputs={},
    )
