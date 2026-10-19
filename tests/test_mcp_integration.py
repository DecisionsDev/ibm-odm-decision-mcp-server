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

"""
Integration tests running DecisionMCPServer against the real `mcp` SDK.

The handlers are wired into a real MCPServer exactly as DecisionMCPServer.start() does,
and exercised through an in-memory MCP client. Only DecisionServerManager is mocked.
"""

from unittest.mock import Mock

import pytest
from mcp.client import Client
from mcp.server import MCPServer
from mcp.shared.exceptions import MCPError

from decision_mcp_server.Credentials import Credentials
from decision_mcp_server.DecisionMCPServer import DecisionMCPServer
from decision_mcp_server.DecisionServiceDescription import DecisionServiceDescription

TOOL_NAME = "loan_validation"


def _description() -> DecisionServiceDescription:
    return DecisionServiceDescription(
        tool_name=TOOL_NAME,
        ruleset={"id": "loan/1.0/validation/1.0"},
        description="Validate a loan",
        input_schema={"type": "object", "properties": {"amount": {"type": "integer"}}},
    )


def _build(trace_enable=False, traces_dir=None):
    credentials = Credentials(odm_url="http://test:9060/res", username="u", password="p")
    decision_server = DecisionMCPServer(
        console_credentials=credentials,
        runtime_credentials=credentials,
        trace_enable=trace_enable,
        traces_dir=traces_dir,
    )
    manager = Mock()
    manager.fetch_rulesets.return_value = []
    manager.generate_tools_format.return_value = [_description()]
    decision_server.manager = manager

    # Same wiring as DecisionMCPServer.start()
    sdk_server = MCPServer(name="test")
    sdk_server.read_resource = decision_server.read_resource
    sdk_server.list_resources = decision_server.list_resources
    sdk_server.list_tools = decision_server.list_tools
    sdk_server.call_tool = decision_server.call_tool
    return decision_server, manager, sdk_server


@pytest.fixture
def wiring():
    return _build()


@pytest.mark.asyncio
async def test_list_tools_through_sdk(wiring):
    _, _, sdk_server = wiring
    async with Client(sdk_server) as client:
        result = await client.list_tools()
    assert [t.name for t in result.tools] == [TOOL_NAME]
    assert result.tools[0].description == "Validate a loan"


@pytest.mark.asyncio
async def test_call_tool_through_sdk(wiring):
    _, manager, sdk_server = wiring
    manager.invokeDecisionService.return_value = {"approved": True, "__DecisionID__": "42"}
    async with Client(sdk_server) as client:
        await client.list_tools()
        result = await client.call_tool(TOOL_NAME, {"amount": 100})
    assert not result.is_error
    assert '"approved": true' in result.content[0].text
    assert "__DecisionID__" not in result.content[0].text
    assert manager.invokeDecisionService.call_args.kwargs["rulesetPath"] == "/loan/1.0/validation/1.0"
    assert manager.invokeDecisionService.call_args.kwargs["decisionInputs"] == {"amount": 100}


@pytest.mark.asyncio
async def test_call_tool_execution_failure_is_reported_as_error(wiring):
    _, manager, sdk_server = wiring
    manager.invokeDecisionService.side_effect = RuntimeError("boom")
    async with Client(sdk_server) as client:
        await client.list_tools()
        result = await client.call_tool(TOOL_NAME, {})
    assert result.is_error
    assert "boom" in result.content[0].text


@pytest.mark.asyncio
async def test_call_unknown_tool_is_reported_as_error(wiring):
    _, _, sdk_server = wiring
    async with Client(sdk_server) as client:
        result = await client.call_tool("nope", {})
    assert result.is_error
    assert "Unknown tool: nope" in result.content[0].text


@pytest.mark.asyncio
async def test_list_resources_through_sdk(wiring):
    _, _, sdk_server = wiring
    async with Client(sdk_server) as client:
        assert (await client.list_resources()).resources == []
        await client.list_tools()
        result = await client.list_resources()
    assert [str(r.uri) for r in result.resources] == [f"decisionservice://internal/{TOOL_NAME}"]
    assert result.resources[0].mime_type == "text/plain"


@pytest.mark.asyncio
async def test_read_resource_through_sdk(wiring):
    _, _, sdk_server = wiring
    async with Client(sdk_server) as client:
        await client.list_tools()
        result = await client.read_resource(f"decisionservice://internal/{TOOL_NAME}")
    assert len(result.contents) == 1
    assert "loan/1.0/validation/1.0" in result.contents[0].text


@pytest.mark.asyncio
async def test_read_unknown_resource_returns_mcp_error(wiring):
    _, _, sdk_server = wiring
    async with Client(sdk_server) as client:
        with pytest.raises(MCPError):
            await client.read_resource("decisionservice://internal/missing")


@pytest.mark.asyncio
async def test_read_resource_unsupported_scheme_returns_mcp_error(wiring):
    _, _, sdk_server = wiring
    async with Client(sdk_server) as client:
        with pytest.raises(MCPError):
            await client.read_resource("http://internal/whatever")


@pytest.mark.asyncio
async def test_execution_traces_enabled(tmp_path):
    decision_server, manager, _ = _build(trace_enable=True, traces_dir=str(tmp_path))
    manager.invokeDecisionService.return_value = {"approved": True, "__DecisionID__": "42"}
    await decision_server.list_tools()
    await decision_server.call_tool(TOOL_NAME, {"amount": 100}, None)

    resources = await decision_server.list_execution_traces()
    assert len(resources) == 1
    assert str(resources[0].uri).startswith("trace://")

    trace_id = str(resources[0].uri).removeprefix("trace://")
    trace = await decision_server.get_execution_trace(trace_id)
    assert trace is not None
    assert trace.tool_name == TOOL_NAME
    assert trace.decision_id == "42"
    assert trace.inputs == {"amount": 100}
