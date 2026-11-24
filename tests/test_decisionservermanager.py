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
from decision_mcp_server.DecisionServerManager import DecisionServerManager  # Correct import path
from http.server import BaseHTTPRequestHandler, HTTPServer
from decision_mcp_server.Credentials import Credentials  # Correct import path
import json
import threading

# Mock data to be returned by the server
mock_data = [
    {
        "id": "checktoolsparam/1.0",
        "rulesets": [
            # This ruleset has a agent.parameters property
            {"id": "checktoolsparam/1.0/ruleset1", "properties": [{"id":"ruleset.status","value":"enabled"},{"id":"agent.enabled","value":"true"}], "version": "1.0","test":"true"},
            {"id": "checktoolsparam/1.0/ruleset2", "properties": [{"id":"ruleset.status","value":"enabled"}],"version": "2.0","test":"false"}
        ]
    },
    {
        "id": "verifystatusenabled/1.0",
        "rulesets": [
            # This ruleset has an enabled status
            {"id": "verifystatusenabled/1.0/ruleset1", "properties": [{"id":"ruleset.status","value":"enabled"},{"id":"agent.enabled","value":"true"}], "version": "1.0","test":"true"},
            # This ruleset has an enabled status - Should be selected
            {"id": "verifystatusenabled/1.0/ruleset1", "properties": [{"id":"ruleset.status","value":"enabled"},{"id":"agent.enabled","value":"true"}], "version": "2.0","test":"true"},
            # This ruleset has a disabled status
            {"id": "verifystatusenabled/1.0/ruleset1", "properties": [{"id":"ruleset.status","value":"disabled"},{"id":"agent.enabled","value":"true"}],"version": "3.0","test":"false"}
        ]
    },
    {
        "id": "multipleruleset/1.0",
        "rulesets": [
            {"id": "multipleruleset/1.0/ruleset1","properties": [{"id":"ruleset.status","value":"enabled"},{"id":"agent.enabled","value":"true"}], "version": "1.1","test":"true"},
            {"id": "multipleruleset/1.0/ruleset2","properties": [{"id":"ruleset.status","value":"enabled"},{"id":"agent.enabled","value":"true"}], "version": "1.2","test":"true"}
        ]
    },
    {
        "id": "minorrulesetversion/1.0",
        "rulesets": [
            {"id": "minorrulesetversion/1.0/ruleset1","properties": [{"id":"ruleset.status","value":"enabled"},{"id":"agent.parameters","value":"{\"arg\":\"name\"}"}], "version": "1.1","test":"true"},
            {"id": "minorrulesetversion/1.0/ruleset1","properties": [{"id":"ruleset.status","value":"enabled"},{"id":"agent.enabled","value":"true"}],"version": "1.2","test":"true"}
        ]
    }
]

class MockServerRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/res/api/v1/ruleapps':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(mock_data).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def run_mock_server(server_class=HTTPServer, handler_class=MockServerRequestHandler, port=8885):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()

@pytest.fixture(scope='module', autouse=True)
def mock_server():
    # Start the mock server in a separate thread
    mock_server_thread = threading.Thread(target=run_mock_server)
    mock_server_thread.daemon = True
    mock_server_thread.start()
    yield
    # Cleanup code can be added here if needed

def test_fetch_rulesets(caplog):
    import os
    # Use environment variables or default to mock values for testing
    credentials = Credentials(
        odm_url='http://localhost:8885/res',
        username=os.environ.get('TEST_USERNAME', 'mock_bearer_token'),
        password=os.environ.get('TEST_PASSWORD', 'mock_password_placeholder'),
)
    manager = DecisionServerManager(
        console_credentials=credentials,
        runtime_credentials=credentials
    )

    # Capture the output of the fetch_rulesets method
#    with caplog.at_level(logging.INFO):
#        manager.fetch_rulesets()
    ruleset_fetched = manager.fetch_rulesets()
    # Verify the rulesets contain the expected output

    fetchedresult={}
    if ruleset_fetched:  # Check if ruleset_fetched is not None
        for ruleset in ruleset_fetched.values():
            fetchedresult[ruleset["id"]]=ruleset["properties"]

    print("RESULT : "+str(fetchedresult))


    def filter_rulesets(mock_data):
        filtered_data = []
        result_tocheck = {}
        for app in mock_data:
            filtered_rulesets = []
            for ruleset in app["rulesets"]:
                if ruleset.get("test") == "true":
                    ruleset_copy = ruleset.copy()
                    del ruleset_copy["test"]
                    filtered_rulesets.append(ruleset_copy)
                    result_tocheck[ruleset["id"]]=ruleset_copy['properties']
                    
            
            if filtered_rulesets:
                filtered_data.append({
                    "id": app["id"],
                    "rulesets": filtered_rulesets
                })   
        return result_tocheck

    expected_rulesets = filter_rulesets(mock_data)

    # Extract the dictionary
    assert len(fetchedresult) == len(expected_rulesets)

    # Make sure you sort any lists in the dictionary before dumping to a string

    resultsort = json.dumps(fetchedresult, sort_keys=True)
    expectedsort = json.dumps(expected_rulesets, sort_keys=True)

    assert resultsort == expectedsort
    # Verify the logs contain the expected output
 #   log_output = caplog.text
 #   assert "RuleApp: ruleapp1, Ruleset: ruleset1, Highest Version Ruleset: ruleapp1/1.0/ruleset2" in log_output
 #   assert "RuleApp: ruleapp2, Ruleset: ruleset2, Highest Version Ruleset: ruleapp2/1.0/ruleset2" in log_output

def test_get_input_schema():
    """
    Test that get_input_schema always uses the OpenAPI generation.
    """
    # Create a test ruleset
    ruleset = {
        "id": "test/1.0/ruleset",
        "properties": []
    }
    
    # Create a mock DecisionServerManager with a mocked get_ruleset_openapi method
    import os
    # Use environment variables or default to mock values for testing
    credentials = Credentials(
        odm_url='http://localhost:8885/res',
        username=os.environ.get('TEST_USERNAME', 'mock_bearer_token'),
        password=os.environ.get('TEST_PASSWORD', 'mock_password_placeholder'),
    )
    
    manager = DecisionServerManager(console_credentials=credentials,
                                    runtime_credentials=credentials)
    
    # Mock the get_ruleset_openapi method
    original_get_ruleset_openapi = manager.get_ruleset_openapi
    openapi_called = [False]  # Using a list to track if the method was called
    
    def mock_get_ruleset_openapi(ruleset):
        openapi_called[0] = True
        return {"type": "object", "properties": {"mocked": {"type": "string"}}}
    
    manager.get_ruleset_openapi = mock_get_ruleset_openapi
    
    try:
        # Call get_input_schema
        result = manager.get_input_schema(ruleset)
        
        # Check that get_ruleset_openapi was called
        assert openapi_called[0] == True
        
        # Verify the result is the mocked OpenAPI schema
        assert result == {"type": "object", "properties": {"mocked": {"type": "string"}}}
    
    finally:
        # Restore the original method
        manager.get_ruleset_openapi = original_get_ruleset_openapi

def test_agent_name_handling():
    """Test the handling of agent.name property in generate_tools_format method."""
    # Create test data with two rulesets - one with agent.name and one without
    rulesets = {
        "ruleset1": {
            "id": "test/1.0/ruleset1",
            "displayName": "Display Name With Spaces",
            "description": "Test description",
            "properties": [
                {"id": "agent.enabled", "value": "true"},
                {"id": "agent.parameters", "value": '{"type":"object","properties":{"name":{"type":"string"}}}'},
                # No agent.name here - should use displayName
            ]
        },
        "ruleset2": {
            "id": "test/1.0/ruleset2",
            "displayName": "Unused Display Name",
            "description": "Test description 2",
            "properties": [
                {"id": "agent.enabled", "value": "true"},
                {"id": "agent.parameters", "value": '{"type":"object","properties":{"name":{"type":"string"}}}'},
                {"id": "agent.name", "value": "CustomToolName"},  # Explicit agent.name
            ]
        }
    }
    
    # Create a mock DecisionServerManager
    import os
    # Use environment variables or default to mock values for testing
    credentials = Credentials(
        odm_url='http://localhost:8885/res',
        username=os.environ.get('TEST_USERNAME', 'mock_user'),
        password=os.environ.get('TEST_PASSWORD', 'mock_password_placeholder'),
    )
    
    manager = DecisionServerManager(console_credentials=credentials,
                                    runtime_credentials=credentials)
    
    # Mock the get_input_schema method to return a simple schema
    original_get_input_schema = manager.get_input_schema
    
    def mock_get_input_schema(ruleset):
        return {"type": "object", "properties": {"name": {"type": "string"}}}
    
    manager.get_input_schema = mock_get_input_schema
    
    try:
        # Call generate_tools_format
        result = manager.generate_tools_format(rulesets)
        
        # Verify both tools were formatted correctly, keyed by tool name and sorted by key
        assert list(result) == ["CustomToolName", "Display_Name_With_Spaces"]
        
        # First ruleset should use displayName (spaces replaced by underscores, case preserved)
        assert result["Display_Name_With_Spaces"].tool_name == "Display_Name_With_Spaces"
        
        # Second ruleset should use the explicit agent.name
        assert result["CustomToolName"].tool_name == "CustomToolName"
        
    finally:
        # Restore the original method
        manager.get_input_schema = original_get_input_schema

def test_tools_name_and_description_handling():
    """
    Test that agent.name and agent.description properties are correctly handled
    in the generate_tools_format method.
    """
    # Create test data with three rulesets to test different scenarios
    rulesets = {
        "ruleset1": {
            "id": "test/1.0/ruleset1",
            "displayName": "Display Name With Spaces",
            "description": "Default description",
            "properties": [
                {"id": "agent.enabled", "value": "true"},
                # No agent.name or agent.description - should use defaults
            ]
        },
        "ruleset2": {
            "id": "test/1.0/ruleset2",
            "displayName": "Unused Display Name",
            "description": "Unused description",
            "properties": [
                {"id": "agent.enabled", "value": "true"},
                {"id": "agent.name", "value": "CustomToolName"},  # Custom name
                {"id": "agent.description", "value": "Custom description"},  # Custom description
            ]
        },
        "ruleset3": {
            "id": "test/1.0/ruleset3",
            "displayName": "Another Display Name",
            "description": "Another default description",
            "properties": [
                {"id": "agent.enabled", "value": "true"},
                {"id": "agent.name", "value": "ThirdTool"},  # Custom name
                # No agent.description - should fall back to default
            ]
        }
    }
    
    # Create a mock DecisionServerManager
    import os
    # Use environment variables or default to mock values for testing
    credentials = Credentials(
        odm_url='http://localhost:8885/res',
        username=os.environ.get('TEST_USERNAME', 'mock_user'),
        password=os.environ.get('TEST_PASSWORD', 'mock_password_placeholder'),
    )
    
    manager = DecisionServerManager(console_credentials=credentials,
                                    runtime_credentials=credentials)
    
    # Mock the get_input_schema method to return a simple schema
    original_get_input_schema = manager.get_input_schema
    
    def mock_get_input_schema(ruleset):
        return {"type": "object", "properties": {"name": {"type": "string"}}}
    
    manager.get_input_schema = mock_get_input_schema
    
    try:
        # Call generate_tools_format
        result = manager.generate_tools_format(rulesets)
        
        # Verify all tools were formatted correctly, keyed by tool name and sorted by key
        assert list(result) == ["CustomToolName", "Display_Name_With_Spaces", "ThirdTool"]
        
        # First ruleset should use displayName and default description
        assert result["Display_Name_With_Spaces"].tool_name == "Display_Name_With_Spaces"
        assert result["Display_Name_With_Spaces"].description == "Default description"
        
        # Second ruleset should use explicit values for both name and description
        assert result["CustomToolName"].tool_name == "CustomToolName"  # Note: the case is preserved
        assert result["CustomToolName"].description == "Custom description"
        
        # Third ruleset should use explicit name but default description
        assert result["ThirdTool"].tool_name == "ThirdTool"  # Note: the case is preserved
        assert result["ThirdTool"].description == "Another default description"
        
        # Verify rulesetPath is set correctly
        assert result["Display_Name_With_Spaces"].rulesetPath == "/test/1.0/ruleset1"
        assert result["CustomToolName"].rulesetPath == "/test/1.0/ruleset2"
        assert result["ThirdTool"].rulesetPath == "/test/1.0/ruleset3"
        
    finally:
        # Restore the original method
        manager.get_input_schema = original_get_input_schema


def _manager_with_mocked_schema() -> DecisionServerManager:
    credentials = Credentials(odm_url='http://localhost:8885/res', username='mock_user', password='mock_password_placeholder')
    manager = DecisionServerManager(console_credentials=credentials, runtime_credentials=credentials)
    manager.get_input_schema = lambda ruleset: {"type": "object", "properties": {}}
    return manager

def _ruleset(ruleset_id: str, name: str) -> dict:
    return {
        "id": ruleset_id,
        "displayName": name,
        "description": "description",
        "properties": [{"id": "agent.enabled", "value": "true"}],
    }

def test_generate_tools_format_renames_duplicate_tool_names(caplog):
    """All the rulesets sharing a tool name are renamed <name>_<n>_<ruleapp>_<ruleset>, and a warning is logged."""
    rulesets = {
        "b": _ruleset("Loan App/1.0/Validation/1.0", "Check"),
        "a": _ruleset("insurance/2.0/eligibility/1.0", "Check"),
        "c": _ruleset("other/1.0/unique/1.0", "Unique"),
    }

    with caplog.at_level("WARNING"):
        result = _manager_with_mocked_schema().generate_tools_format(rulesets)

    assert list(result) == ["Check_1_Loan_App_Validation", "Check_1_insurance_eligibility", "Unique"]
    assert result["Check_1_Loan_App_Validation"].tool_name == "Check_1_Loan_App_Validation"
    assert result["Check_1_Loan_App_Validation"].rulesetPath == "/Loan App/1.0/Validation/1.0"
    assert result["Check_1_insurance_eligibility"].rulesetPath == "/insurance/2.0/eligibility/1.0"
    assert "Check_1_Loan_App_Validation" in caplog.text
    assert "Check_1_insurance_eligibility" in caplog.text

def test_generate_tools_format_tool_names_are_case_sensitive():
    """Names differing only by case are distinct tools: they are not renamed."""
    rulesets = {"a": _ruleset("app/1.0/rs1/1.0", "Check"), "b": _ruleset("app/1.0/rs2/1.0", "check")}

    result = _manager_with_mocked_schema().generate_tools_format(rulesets)

    assert list(result) == ["Check", "check"]

def test_generate_tools_format_replaces_invalid_characters():
    """Characters other than ASCII letters, digits, '_', '-' and '.' are replaced by '_'."""
    rulesets = {"a": _ruleset("app/1.0/rs/1.0", "Loan v1.0-beta: é/ü")}

    result = _manager_with_mocked_schema().generate_tools_format(rulesets)

    assert list(result) == ["Loan_v1.0-beta_____"]

def test_generate_tools_format_limits_tool_names_to_64_characters():
    """When the name alone fills the 64 characters, the tail is dropped and the name is shortened for the number."""
    rulesets = {
        "a": _ruleset("app/1.0/rs1/1.0", "x" * 200),
        "b": _ruleset("app/1.0/rs2/1.0", "x" * 200),
    }

    result = _manager_with_mocked_schema().generate_tools_format(rulesets)

    assert all(len(name) <= 64 for name in result)
    assert sorted(result) == [f"{'x' * 62}_1", f"{'x' * 62}_2"]

def test_generate_tools_format_drops_tail_when_it_does_not_fit():
    """The <ruleapp>_<ruleset> tail is dropped altogether if it does not fit in 64 characters."""
    rulesets = {
        "a": _ruleset(f"{'a' * 40}/1.0/{'b' * 40}/1.0", "dup"),
        "b": _ruleset(f"{'c' * 40}/1.0/{'b' * 40}/1.0", "dup"),
    }

    result = _manager_with_mocked_schema().generate_tools_format(rulesets)

    assert sorted(result) == ["dup_1", "dup_2"]

def test_generate_tools_format_truncates_unique_tool_names_to_64_characters():
    rulesets = {"a": _ruleset("app/1.0/rs/1.0", "y" * 100)}

    result = _manager_with_mocked_schema().generate_tools_format(rulesets)

    assert list(result) == ["y" * 64]

def test_generate_tools_format_increments_suffix_when_renamed_tool_is_taken():
    """The number is incremented when <name>_1_<ruleapp>_<ruleset> collides with another tool name."""
    rulesets = {
        "first": _ruleset("app/1.0/rs/1.0", "dup"),
        "second": _ruleset("app/2.0/rs/1.0", "dup"),
        "taken": _ruleset("app/3.0/other/1.0", "dup_1_app_rs"),
    }

    result = _manager_with_mocked_schema().generate_tools_format(rulesets)

    assert list(result) == ["dup_1_app_rs", "dup_2_app_rs", "dup_3_app_rs"]
    assert result["dup_1_app_rs"].rulesetPath == "/app/3.0/other/1.0"
    assert {result["dup_2_app_rs"].rulesetPath, result["dup_3_app_rs"].rulesetPath} == {
        "/app/1.0/rs/1.0", "/app/2.0/rs/1.0"
    }

def test_generate_tools_format_does_not_warn_without_duplicates(caplog):
    rulesets = {"a": _ruleset("app/1.0/rs1/1.0", "one"), "b": _ruleset("app/1.0/rs2/1.0", "two")}

    with caplog.at_level("WARNING"):
        _manager_with_mocked_schema().generate_tools_format(rulesets)

    assert "is used by several rulesets" not in caplog.text



def test_extract_highest_version_rulesets_agent_enabled():
    """Test that only rulesets with agent.enabled=true are included."""
    
    # Create test data with various agent.enabled values
    test_data = [
        {
            "id": "app1/1.0",
            "rulesets": [
                {
                    "id": "app1/1.0/ruleset1",
                    "version": "1.9",
                    "displayName": "Ruleset 1",
                    "description": "Test ruleset 1",
                    "properties": [
                        {"id": "ruleset.status", "value": "enabled"},
                        {"id": "agent.enabled", "value": "true"}  # This one is superseded
                    ]
                },
                {
                    "id": "app1/1.0/ruleset1",
                    "version": "1.10",
                    "displayName": "Ruleset 1",
                    "description": "Test ruleset 1",
                    "properties": [
                        {"id": "ruleset.status", "value": "enabled"},
                        {"id": "agent.enabled", "value": "true"}  # This should be included
                    ]
                },
                {
                    "id": "app1/1.0/ruleset2",
                    "version": "1.0",
                    "displayName": "Ruleset 2",
                    "description": "Test ruleset 2",
                    "properties": [
                        {"id": "ruleset.status", "value": "enabled"},
                        {"id": "agent.enabled", "value": "false"}  # This should be excluded
                    ]
                }
            ]
        },
        {
            "id": "app2/1.0",
            "rulesets": [
                {
                    "id": "app2/1.0/ruleset3",
                    "version": "1.0",
                    "displayName": "Ruleset 3",
                    "description": "Test ruleset 3",
                    "properties": [
                        {"id": "ruleset.status", "value": "enabled"},
                        {"id": "agent.enabled", "value": "TRUE"}  # This should be included (case-insensitive)
                    ]
                },
                {
                    "id": "app2/1.0/ruleset4",
                    "version": "1.0",
                    "displayName": "Ruleset 4",
                    "description": "Test ruleset 4",
                    "properties": [
                        {"id": "ruleset.status", "value": "enabled"}
                        # No agent.enabled property - should be excluded
                    ]
                }
            ]
        },
        {
            "id": "app3/1.0",
            "rulesets": [
                {
                    "id": "app3/1.0/ruleset5",
                    "version": "1.0",
                    "displayName": "Ruleset 5",
                    "description": "Test ruleset 5",
                    "properties": [
                        {"id": "ruleset.status", "value": "enabled"},
                        {"id": "agent.enabled", "value": "yes"}  # Non-standard value - should be excluded
                    ]
                }
            ]
        }
    ]
    
    # Create a mock DecisionServerManager
    import os
    # Use environment variables or default to mock values for testing
    credentials = Credentials(
        odm_url='http://localhost:8885/res',
        username=os.environ.get('TEST_USERNAME', 'mock_user'),
        password=os.environ.get('TEST_PASSWORD', 'mock_password_placeholder'),
    )
    
    manager = DecisionServerManager(console_credentials=credentials,
                                    runtime_credentials=credentials)
    
    # Call extract_highest_version_rulesets
    result = manager.extract_highest_version_rulesets(test_data)
    print(result)
    # Verify only rulesets with agent.enabled=true (case-insensitive) are included
    assert len(result) == 2
    assert "app1ruleset1" in result
    assert "app2ruleset3" in result
    
    # Verify rulesets with agent.enabled=false, missing agent.enabled, or non-standard values are excluded
    assert "app1ruleset2" not in result
    assert "app2ruleset4" not in result
    assert "app3ruleset5" not in result

    # verify that the version of app1ruleset1 is 1.10 not 1.9
    assert result["app1ruleset1"]["version"] == "1.10"

# Run the tests
if __name__ == '__main__':
    pytest.main()


def _mock_credentials(cacert):
    from unittest.mock import MagicMock
    creds = MagicMock()
    creds.odm_url = 'https://odm.example.com/res'
    creds.cacert = cacert
    return creds


def test_fetch_rulesets_passes_cacert_to_session_get():
    """fetch_rulesets must pass the console credentials' CA bundle (certifi by default) as verify=."""
    import certifi
    console = _mock_credentials(certifi.where())
    response = console.get_session.return_value.get.return_value
    response.status_code = 200
    response.json.return_value = []
    manager = DecisionServerManager(console_credentials=console, runtime_credentials=_mock_credentials(None))

    manager.fetch_rulesets()

    kwargs = console.get_session.return_value.get.call_args.kwargs
    assert kwargs['verify'] == certifi.where()


def test_get_ruleset_openapi_passes_cacert_to_session_get():
    """get_ruleset_openapi must pass the runtime credentials' CA bundle as verify=."""
    import certifi
    from mcp.server.mcpserver.exceptions import ToolError
    runtime = _mock_credentials(certifi.where())
    response = runtime.get_session.return_value.get.return_value
    response.status_code = 404
    response.text = 'not found'
    manager = DecisionServerManager(console_credentials=_mock_credentials(None), runtime_credentials=runtime)

    with pytest.raises(ToolError):
        manager.get_ruleset_openapi({"id": "app/1.0/rs/1.0"})

    kwargs = runtime.get_session.return_value.get.call_args.kwargs
    assert kwargs['verify'] == certifi.where()
