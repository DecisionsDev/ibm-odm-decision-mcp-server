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
        
        # Verify both tools were formatted correctly
        assert len(result) == 2
        
        # First ruleset should use displayName (converted to lowercase with underscores)
        assert result[0].tool_name == "display_name_with_spaces"
        
        # Second ruleset should use the explicit agent.name
        assert result[1].tool_name == "customtoolname"
        
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
        
        # Verify all tools were formatted correctly
        assert len(result) == 3
        
        # First ruleset should use displayName and default description
        assert result[0].tool_name == "display_name_with_spaces"
        assert result[0].description == "Default description"
        
        # Second ruleset should use explicit values for both name and description
        assert result[1].tool_name == "customtoolname"  # Note: also tests lowercase conversion
        assert result[1].description == "Custom description"
        
        # Third ruleset should use explicit name but default description
        assert result[2].tool_name == "thirdtool"  # Note: also tests lowercase conversion
        assert result[2].description == "Another default description"
        
        # Verify rulesetPath is set correctly
        assert result[0].rulesetPath == "/test/1.0/ruleset1"
        assert result[1].rulesetPath == "/test/1.0/ruleset2"
        assert result[2].rulesetPath == "/test/1.0/ruleset3"
        
    finally:
        # Restore the original method
        manager.get_input_schema = original_get_input_schema

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
    assert "app1/ruleset1" in result
    assert "app2/ruleset3" in result
    
    # Verify rulesets with agent.enabled=false, missing agent.enabled, or non-standard values are excluded
    assert "app1/ruleset2" not in result
    assert "app2/ruleset4" not in result
    assert "app3/ruleset5" not in result

    # verify that the version of app1/ruleset1 is 1.10 not 1.9
    assert result["app1/ruleset1"]["version"] == "1.10"

# Run the tests
if __name__ == '__main__':
    pytest.main()
