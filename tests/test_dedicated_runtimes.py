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

import argparse
import pytest
from unittest.mock import Mock, patch

from decision_mcp_server.DecisionMCPServer import (
    DecisionMCPServer,
    _dedicated_runtime_pair,
    parse_arguments,
)
from decision_mcp_server.Credentials import Credentials
from decision_mcp_server.DecisionServerManager import DecisionServerManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _basic_credentials(url: str) -> Credentials:
    return Credentials(odm_url=url, username="user", password="pass", verify_ssl=False)


def _make_server(dedicated_runtimes=None):
    console = _basic_credentials("http://console:9060/res")
    runtime = _basic_credentials("http://default-runtime:9060/DecisionService")
    return DecisionMCPServer(
        console_credentials=console,
        runtime_credentials=runtime,
        dedicated_runtimes=dedicated_runtimes,
    )


# ---------------------------------------------------------------------------
# _dedicated_runtime_pair — argument type helper
# ---------------------------------------------------------------------------

class TestDedicatedRuntimePair:

    def test_valid_pair(self):
        result = _dedicated_runtime_pair("/app/1.0/ruleset/1.0=http://runtime:9060/DecisionService")
        assert result == ("/app/1.0/ruleset/1.0", "http://runtime:9060/DecisionService")

    def test_strips_whitespace(self):
        result = _dedicated_runtime_pair("  /app/path  =  http://runtime:9060/DecisionService  ")
        assert result == ("/app/path", "http://runtime:9060/DecisionService")

    def test_url_with_embedded_equals_sign(self):
        """Only the first '=' is used as separator; the rest belongs to the URL."""
        result = _dedicated_runtime_pair("/path=http://host/svc?token=abc")
        assert result == ("/path", "http://host/svc?token=abc")

    def test_missing_equals_raises(self):
        with pytest.raises(argparse.ArgumentTypeError) as exc_info:
            _dedicated_runtime_pair("no-separator-here")
        assert "Expected rulesetPath=serverURL" in str(exc_info.value)

    def test_empty_string_raises(self):
        with pytest.raises(argparse.ArgumentTypeError):
            _dedicated_runtime_pair("")


# ---------------------------------------------------------------------------
# parse_arguments — --dedicated-runtimes CLI flag
# ---------------------------------------------------------------------------

class TestParseArgumentsDedicatedRuntimes:

    def test_single_pair(self):
        with patch("sys.argv", ["script",
                                "--dedicated-runtimes",
                                "/app/1.0/ruleset/1.0=http://rt:9060/DecisionService"]):
            args = parse_arguments()
        assert args.dedicated_runtimes == [("/app/1.0/ruleset/1.0", "http://rt:9060/DecisionService")]

    def test_multiple_pairs_single_flag(self):
        with patch("sys.argv", ["script",
                                "--dedicated-runtimes",
                                "/a/1.0/r/1.0=http://rt1:9060/DecisionService",
                                "/b/1.0/r/1.0=http://rt2:9060/DecisionService"]):
            args = parse_arguments()
        assert len(args.dedicated_runtimes) == 2
        assert args.dedicated_runtimes[0] == ("/a/1.0/r/1.0", "http://rt1:9060/DecisionService")
        assert args.dedicated_runtimes[1] == ("/b/1.0/r/1.0", "http://rt2:9060/DecisionService")

    def test_underscore_alias(self):
        with patch("sys.argv", ["script",
                                "--dedicated_runtimes",
                                "/app/1.0/r/1.0=http://rt:9060/DecisionService"]):
            args = parse_arguments()
        assert args.dedicated_runtimes == [("/app/1.0/r/1.0", "http://rt:9060/DecisionService")]

    def test_default_is_empty_list(self):
        with patch("sys.argv", ["script"]), patch.dict("os.environ", {}, clear=True):
            args = parse_arguments()
        assert args.dedicated_runtimes == []

    def test_invalid_pair_exits(self):
        with patch("sys.argv", ["script", "--dedicated-runtimes", "no-equals"]):
            with pytest.raises(SystemExit):
                parse_arguments()


# ---------------------------------------------------------------------------
# DecisionMCPServer.__init__ — credential objects creation & deduplication
# ---------------------------------------------------------------------------

class TestDedicatedRuntimesInit:

    def test_no_dedicated_runtimes(self):
        server = _make_server()
        assert server.dedicated_runtime_credentials == {}

    def test_none_dedicated_runtimes(self):
        server = _make_server(dedicated_runtimes=None)
        assert server.dedicated_runtime_credentials == {}

    def test_single_dedicated_runtime_registered(self):
        server = _make_server(
            dedicated_runtimes=[("/app/1.0/r/1.0", "http://dedicated:9060/DecisionService")]
        )
        assert "/app/1.0/r/1.0" in server.dedicated_runtime_credentials
        creds = server.dedicated_runtime_credentials["/app/1.0/r/1.0"]
        assert isinstance(creds, Credentials)
        assert creds.odm_url == "http://dedicated:9060/DecisionService"

    def test_dedicated_credentials_inherit_auth_from_runtime(self):
        console = _basic_credentials("http://console:9060/res")
        runtime = Credentials(
            odm_url="http://default-runtime:9060/DecisionService",
            username="rt_user",
            password="rt_pass",
            verify_ssl=False,
        )
        server = DecisionMCPServer(
            console_credentials=console,
            runtime_credentials=runtime,
            dedicated_runtimes=[("/app/1.0/r/1.0", "http://dedicated:9060/DecisionService")],
        )
        creds = server.dedicated_runtime_credentials["/app/1.0/r/1.0"]
        # URL is overridden
        assert creds.odm_url == "http://dedicated:9060/DecisionService"
        # Auth settings are inherited
        assert creds.username == "rt_user"
        assert creds.password == "rt_pass"
        assert creds.verify_ssl is False

    def test_two_paths_same_url_share_one_credentials_object(self):
        """The most important deduplication test: same URL → same object identity."""
        shared_url = "http://shared-runtime:9060/DecisionService"
        server = _make_server(
            dedicated_runtimes=[
                ("/app1/1.0/r/1.0", shared_url),
                ("/app2/1.0/r/1.0", shared_url),
                ("/app3/1.0/r/1.0", shared_url),
            ]
        )
        creds_1 = server.dedicated_runtime_credentials["/app1/1.0/r/1.0"]
        creds_2 = server.dedicated_runtime_credentials["/app2/1.0/r/1.0"]
        creds_3 = server.dedicated_runtime_credentials["/app3/1.0/r/1.0"]
        # All three paths must reference the exact same object
        assert creds_1 is creds_2
        assert creds_2 is creds_3

    def test_two_paths_different_urls_have_distinct_credentials_objects(self):
        server = _make_server(
            dedicated_runtimes=[
                ("/app1/1.0/r/1.0", "http://rt-a:9060/DecisionService"),
                ("/app2/1.0/r/1.0", "http://rt-b:9060/DecisionService"),
            ]
        )
        creds_a = server.dedicated_runtime_credentials["/app1/1.0/r/1.0"]
        creds_b = server.dedicated_runtime_credentials["/app2/1.0/r/1.0"]
        assert creds_a is not creds_b
        assert creds_a.odm_url == "http://rt-a:9060/DecisionService"
        assert creds_b.odm_url == "http://rt-b:9060/DecisionService"

    def test_mixed_shared_and_distinct_urls(self):
        shared_url = "http://shared:9060/DecisionService"
        server = _make_server(
            dedicated_runtimes=[
                ("/path1=", shared_url),           # shares
                ("/path2=", shared_url),           # shares
                ("/path3=", "http://other:9060/DecisionService"),  # distinct
            ]
        )
        assert server.dedicated_runtime_credentials["/path1="] is server.dedicated_runtime_credentials["/path2="]
        assert server.dedicated_runtime_credentials["/path1="] is not server.dedicated_runtime_credentials["/path3="]


# ---------------------------------------------------------------------------
# call_tool — routing logic
# ---------------------------------------------------------------------------

class TestCallToolDedicatedRuntimeRouting:

    def _server_with_repo(self, dedicated_runtimes=None):
        """Build a server with a mocked manager and a pre-populated repository."""
        server = _make_server(dedicated_runtimes=dedicated_runtimes)
        server.manager = Mock()
        server.manager.invokeDecisionService.return_value = {"decision": "ok"}
        return server

    def _add_tool(self, server, tool_name, ruleset_path):
        mock_service = Mock()
        mock_service.rulesetPath = ruleset_path
        server.repository[tool_name] = mock_service

    @pytest.mark.asyncio
    async def test_no_dedicated_runtimes_uses_default(self):
        """When no dedicated runtimes are configured, runtime_credentials kwarg is None."""
        server = self._server_with_repo()
        self._add_tool(server, "loan_tool", "/loanApp/1.0/ruleset/1.0")

        await server.call_tool("loan_tool", {"amount": 1000}, {})

        _, kwargs = server.manager.invokeDecisionService.call_args
        assert kwargs["runtime_credentials"] is None

    @pytest.mark.asyncio
    async def test_matching_path_passes_dedicated_credentials(self):
        """A ruleset path that matches a registered prefix routes to the dedicated server."""
        dedicated_url = "http://dedicated:9060/DecisionService"
        server = self._server_with_repo(
            dedicated_runtimes=[("/loanApp/1.0/ruleset/1.0", dedicated_url)]
        )
        self._add_tool(server, "loan_tool", "/loanApp/1.0/ruleset/1.0")

        await server.call_tool("loan_tool", {"amount": 1000}, {})

        _, kwargs = server.manager.invokeDecisionService.call_args
        assert kwargs["runtime_credentials"] is not None
        assert kwargs["runtime_credentials"].odm_url == dedicated_url

    @pytest.mark.asyncio
    async def test_non_matching_path_uses_default(self):
        """A ruleset path that does NOT match any prefix gets None (default runtime)."""
        server = self._server_with_repo(
            dedicated_runtimes=[("/otherApp/1.0/ruleset/1.0", "http://other:9060/DecisionService")]
        )
        self._add_tool(server, "loan_tool", "/loanApp/1.0/ruleset/1.0")

        await server.call_tool("loan_tool", {"amount": 1000}, {})

        _, kwargs = server.manager.invokeDecisionService.call_args
        assert kwargs["runtime_credentials"] is None

    @pytest.mark.asyncio
    async def test_prefix_matching_on_partial_path(self):
        """A registered prefix matches any ruleset path that starts with it."""
        dedicated_url = "http://dedicated:9060/DecisionService"
        server = self._server_with_repo(
            dedicated_runtimes=[("/loanApp/", dedicated_url)]
        )
        self._add_tool(server, "loan_tool", "/loanApp/1.0/ruleset/1.0")

        await server.call_tool("loan_tool", {"amount": 1000}, {})

        _, kwargs = server.manager.invokeDecisionService.call_args
        assert kwargs["runtime_credentials"].odm_url == dedicated_url

    @pytest.mark.asyncio
    async def test_multiple_dedicated_runtimes_first_match_wins(self):
        """The first matching prefix is used; subsequent matches are ignored."""
        url_a = "http://rt-a:9060/DecisionService"
        url_b = "http://rt-b:9060/DecisionService"
        server = self._server_with_repo(
            dedicated_runtimes=[
                ("/loanApp/", url_a),
                ("/loanApp/1.0/", url_b),   # more specific, but listed second
            ]
        )
        self._add_tool(server, "loan_tool", "/loanApp/1.0/ruleset/1.0")

        await server.call_tool("loan_tool", {"amount": 1000}, {})

        _, kwargs = server.manager.invokeDecisionService.call_args
        # First prefix matched
        assert kwargs["runtime_credentials"].odm_url == url_a

    @pytest.mark.asyncio
    async def test_shared_credentials_object_used_for_both_tools(self):
        """Two tools whose paths map to the same URL receive the identical credentials object."""
        shared_url = "http://shared:9060/DecisionService"
        server = self._server_with_repo(
            dedicated_runtimes=[
                ("/app1/1.0/ruleset/1.0", shared_url),
                ("/app2/1.0/ruleset/1.0", shared_url),
            ]
        )
        self._add_tool(server, "tool1", "/app1/1.0/ruleset/1.0")
        self._add_tool(server, "tool2", "/app2/1.0/ruleset/1.0")

        await server.call_tool("tool1", {}, {})
        creds_1 = server.manager.invokeDecisionService.call_args[1]["runtime_credentials"]

        server.manager.invokeDecisionService.reset_mock()
        server.manager.invokeDecisionService.return_value = {"decision": "ok"}

        await server.call_tool("tool2", {}, {})
        creds_2 = server.manager.invokeDecisionService.call_args[1]["runtime_credentials"]

        assert creds_1 is creds_2


# ---------------------------------------------------------------------------
# DecisionServerManager.invokeDecisionService — runtime_credentials override
# ---------------------------------------------------------------------------

class TestInvokeDecisionServiceCredentialsOverride:

    def _manager(self):
        creds = _basic_credentials("http://default:9060/DecisionService")
        return DecisionServerManager(console_credentials=creds, runtime_credentials=creds)

    def _mock_session(self, status_code=200, json_data=None):
        mock_resp = Mock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = json_data or {"result": "ok"}
        mock_session = Mock()
        mock_session.headers = {}
        mock_session.post.return_value = mock_resp
        return mock_session

    def test_default_uses_runtime_credentials(self):
        manager = self._manager()
        mock_session = self._mock_session()
        manager.runtime_credentials.get_session = Mock(return_value=mock_session)
        manager.runtime_credentials.cleanup = Mock()

        manager.invokeDecisionService("/app/1.0/r/1.0", {}, trace=False)

        call_url = mock_session.post.call_args[0][0]
        assert call_url.startswith("http://default:9060/DecisionService")

    def test_override_credentials_used_when_provided(self):
        manager = self._manager()
        dedicated_creds = _basic_credentials("http://dedicated:9060/DecisionService")
        mock_session = self._mock_session()
        dedicated_creds.get_session = Mock(return_value=mock_session)
        dedicated_creds.cleanup = Mock()

        manager.invokeDecisionService("/app/1.0/r/1.0", {}, trace=False,
                                      runtime_credentials=dedicated_creds)

        call_url = mock_session.post.call_args[0][0]
        assert call_url.startswith("http://dedicated:9060/DecisionService")

    def test_override_does_not_affect_default_credentials(self):
        """Passing override credentials must not mutate self.runtime_credentials."""
        manager = self._manager()
        dedicated_creds = _basic_credentials("http://dedicated:9060/DecisionService")
        mock_session = self._mock_session()
        dedicated_creds.get_session = Mock(return_value=mock_session)
        dedicated_creds.cleanup = Mock()

        manager.invokeDecisionService("/app/1.0/r/1.0", {}, trace=False,
                                      runtime_credentials=dedicated_creds)

        assert manager.runtime_credentials.odm_url == "http://default:9060/DecisionService"

    def test_ruleset_path_appended_to_override_url(self):
        manager = self._manager()
        dedicated_creds = _basic_credentials("http://dedicated:9060/DecisionService")
        mock_session = self._mock_session()
        dedicated_creds.get_session = Mock(return_value=mock_session)
        dedicated_creds.cleanup = Mock()

        manager.invokeDecisionService("/myApp/1.0/myRuleset/1.0", {}, trace=False,
                                      runtime_credentials=dedicated_creds)

        call_url = mock_session.post.call_args[0][0]
        assert call_url == "http://dedicated:9060/DecisionService/rest/myApp/1.0/myRuleset/1.0"
