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

import logging
import json
from collections import defaultdict
import requests
import jsonref
from decision_mcp_server.DecisionServiceDescription import DecisionServiceDescription
from mcp.server.mcpserver.exceptions import ToolError
class DecisionServerManager:
    """
    :no-index:
    DecisionServerManager is a class responsible for managing interactions with a decision server, including fetching rulesets, extracting the highest version rulesets, generating tools format, and invoking decision services.

    Methods:
        __init__(self, credentials):
            Initializes the DecisionServerManager with the provided credentials.
        extract_highest_version_rulesets(self, data):
            Extracts the highest version rulesets from the provided data.
        generate_tools_format(self, filtered_rulesets):
            Generates a formatted list of rulesets in the tools format from the filtered rulesets.
        fetch_rulesets(self):
            Fetches rulesets from the decision server and extracts the highest version rulesets.
        invokeDecisionService(self, rulesetPath, decisionInputs):
            Invokes a decision service with the provided ruleset path and decision inputs.

    Usage:
        # Initialize the manager with credentials
        # Example using environment variables (recommended for security)
        import os
        credentials = Credentials(
            odm_url=os.environ.get('ODM_URL'),
            username=os.environ.get('ODM_USERNAME'),
            password=os.environ.get('ODM_PASSWORD')
        )
        manager = DecisionServerManager(credentials)

        # Fetch rulesets
        rulesets = manager.fetch_rulesets()
        print(rulesets)

        # Generate tools format
        formatted_rulesets = manager.generate_tools_format(rulesets)
        print(formatted_rulesets)

        # Invoke decision service
        decision_inputs = {"input1": "value1", "input2": "value2"}
        response = manager.invokeDecisionService('/path/to/ruleset', decision_inputs)
        print(response)
    """
    
    def __init__(self, console_credentials, runtime_credentials):
        """
        :no-index:
        Initializes the DecisionServerManager with the provided credentials.

        Args:
            console_credentials (object): An object containing authentication details for the RES console.
            runtime_credentials (object): An object containing authentication details for the DecisionServer runtime.

        Attributes:
            logger (logging.Logger): Logger instance for logging information.
            console_credentials (object): The provided RES console credentials object.
            runtime_credentials (object): The provided DecisionServer runtime credentials object.
            trace (dict): Trace configuration for logging rule firing information.
        """
        # Get logger for this class
        self.logger = logging.getLogger(__name__)

        # Initialize with provided credentials
        self.console_credentials = console_credentials
        self.runtime_credentials = runtime_credentials
        self.trace={ 
            "__TraceFilter__": {
                "none": True,
                "infoTotalRulesFired": True,
                "infoRulesFired": True
                }
            }
   
    def extract_highest_version_rulesets(self, data):
        """
        :no-index:
        Extracts the highest version rulesets from the provided data.

        Args:
            data (list): A list of rule applications and their rulesets.

        Returns:
            dict: A dictionary containing the highest version rulesets.
        """
        highest_version_rulesets = {}

        # Group rulesets by ruleapp name and ruleset name
        ruleset_groups = defaultdict(list)
        for ruleapp in data:
            ruleapp_name, ruleapp_version = ruleapp["id"].split('/')[0], ruleapp["id"].split('/')[1]
            for ruleset in ruleapp["rulesets"]:
                ruleset_name = ruleset["id"].split('/')[2]
                ruleset_groups[(ruleapp_name, ruleset_name)].append((ruleapp_version, ruleset))

        # Find the highest version ruleset for each group
        for (ruleapp_name, ruleset_name), rulesets in ruleset_groups.items():
            # Sort rulesets by ruleapp version and then by ruleset version
            filtered_rulesets = [
                (version, ruleset) for version, ruleset in rulesets
                     if any(prop["id"] == "ruleset.status" and prop["value"] == "enabled"      for prop in ruleset["properties"])
                    and any(prop["id"] == "agent.enabled"  and prop["value"].lower() == "true" for prop in ruleset["properties"])
            ]
            if not filtered_rulesets:
                continue
            
            # Use numeric version comparison instead of lexicographic string comparison
            sorted_rulesets = sorted(
                filtered_rulesets,
                key=lambda x: (tuple(map(int, x[0].split('.'))), tuple(map(int, x[1]["version"].split('.')))),
                reverse=True
            )

            # Get the highest version ruleset
            highest_version_ruleset = sorted_rulesets[0][1]
            highest_version_rulesets[self.ruleset_key(highest_version_ruleset)] = highest_version_ruleset

        return highest_version_rulesets
    
    def ruleset_key(self, ruleset:dict) -> str:
        l : list[str] = ruleset["id"].split("/")
        return l[0] + "/" + l[2] # ruleapp/ruleset

    def to_plain_dict(self,obj):
        """
        Recursively convert a jsonref.JsonRef structure to a plain JSON-serializable dict, dealing with circular references
        """

        def circular_reference(v,seen_ids):
            if isinstance(v, dict) and v.get("type", "") == "object" and "properties" in v:
                v_id = id(v)
                if v_id in seen_ids:
                    return True # this is a circular reference
                seen_ids.append(v_id)
            return False

        def to_plain_dict(obj,seen_ids):
            if isinstance(obj, dict):
                x = {}
                for k, v in obj.items():
                    seen_ids_copy = seen_ids.copy()
                    if not circular_reference(v,seen_ids_copy):
                        x[k] = to_plain_dict(v,seen_ids_copy)
                return x
            elif isinstance(obj, list):
                return [to_plain_dict(i,seen_ids) for i in obj]
            else:
                return obj

        return to_plain_dict(obj,[])

    def get_ruleset_openapi(self, ruleset):
        """
        :no-index:
        Extracts the input schema from a ruleset.

        Args:
            ruleset (dict): A dictionary representing a ruleset.

        Returns:
            dict: The input schema of the ruleset.
        """
        error = ""
        try:
            # Make the GET request with headers
            path = '/rest/'+ruleset["id"]+ '/openapi?format=json'
            session = self.runtime_credentials.get_session()
            response = session.get(self.runtime_credentials.odm_url+path, headers=session.headers, verify=self.runtime_credentials.cacert)
            self.logger.info(f"{self.runtime_credentials.odm_url}{path} {response.status_code} {len(response.text)}")

            # Check if the request was successful
            if response.status_code == 200:
                # Resolve $ref references
                jsonopenApiData = jsonref.JsonRef.replace_refs(json.loads(response.text))

                # Get the response schema (for 200 response as an example)
                # Extract the input 
                inputParameterSchema= jsonopenApiData["paths"]["/"+ruleset["id"]]["post"]["requestBody"]["content"]["application/json"]["schema"]
                if "properties" in inputParameterSchema and "__DecisionID__" in inputParameterSchema["properties"]:
                    del inputParameterSchema["properties"]["__DecisionID__"]
                # Convert to plain JSON-serializable dict
                return self.to_plain_dict(inputParameterSchema)
            else:
                error = f"Request to {self.runtime_credentials.odm_url}{path} failed (HTTP code {response.status_code}) - Response: {response.text}"

        except requests.exceptions.RequestException as e:
            error = f"Request to {self.runtime_credentials.odm_url}{path} failed: {str(e)}"
        except json.JSONDecodeError as e:
            error = f"Failed to decode the JSON response from {self.runtime_credentials.odm_url}{path}"
        finally:
            self.runtime_credentials.cleanup()
        
        if error:
            self.logger.error(error)
            raise ToolError(error)

    def get_input_schema(self, ruleset):

        """
        :no-index:
        Extracts the input schema from a ruleset using OpenAPI generation.

        Args:
            ruleset (dict): A dictionary representing a ruleset.

        Returns:
            dict: The input schema of the ruleset.
        """
        return self.get_ruleset_openapi(ruleset)
    



    def generate_tools_format(self, filtered_rulesets)-> list[DecisionServiceDescription]:
        """
        :no-index:
        Generates a formatted list of rulesets in the tools format from the filtered rulesets.

        Args:
            filtered_rulesets (dict): A dictionary of filtered rulesets.

        Returns:
            list: A list of formatted rulesets.
        """
        formatted_tools = []

        for ruleset in filtered_rulesets.values():
            input_schema = self.get_input_schema(ruleset)
            toolName = next((prop["value"] for prop in ruleset["properties"] if prop["id"] == "agent.name"), ruleset["displayName"]).replace(" ", "_").lower()
            toolDescription = next((prop["value"] for prop in ruleset["properties"] if prop["id"] == "agent.description"), ruleset["description"])
             # Define a class to hold the formatted ruleset data
            formatted_ruleset = DecisionServiceDescription(toolName, ruleset, toolDescription, input_schema)
            formatted_tools.append(formatted_ruleset)
        return formatted_tools

    def fetch_rulesets(self, ruleset:dict|None = None):
        """
        :no-index:
        Fetches rulesets from the decision server and extracts the highest version rulesets.
        If 'ruleset' is not empty, fetches only the rulesets of the same ruleapp as 'ruleset'.
        Returns:
            dict: A dictionary containing the highest version rulesets, or None if the request fails.
        """
        error = ""
        try:
            # Make the GET request with headers
            path = '/api/v1/ruleapps'
            if ruleset:
                ruleapp = ruleset["id"].split("/")[0]
                path += '/' + ruleapp

            session = self.console_credentials.get_session()
            response = session.get(self.console_credentials.odm_url+path, headers=session.headers, verify=self.console_credentials.cacert)
            self.logger.info(f"{self.console_credentials.odm_url}{path} {response.status_code} {len(response.text)}")

            # Check if the request was successful
            if response.status_code == 200:
                # Parse and display the JSON response
                data = response.json()
                # Extract the highest version rulesets
                highest_version_rulesets = self.extract_highest_version_rulesets(data)

                return highest_version_rulesets
            else:
                error = f"Request to {self.console_credentials.odm_url}{path} failed (HTTP code {response.status_code}) - Response: {response.text}"

        except requests.exceptions.RequestException as e:
            error = f"Request to {self.console_credentials.odm_url}{path} failed: {str(e)}"
        except json.JSONDecodeError:
            error = f"Failed to decode the JSON response from {self.console_credentials.odm_url}{path}"
        finally:
            self.console_credentials.cleanup()
        
        if error:
            self.logger.error(error)
            raise ToolError(error)


    def invokeDecisionService(self, rulesetPath, decisionInputs, trace=True):
        """
        :no-index:
        Invokes a decision service with the provided ruleset path and decision inputs.

        Args:
            rulesetPath (str): The path to the ruleset.
            decisionInputs (dict): A dictionary of decision inputs.

        Returns:
            dict: The response from the decision service, or an error message if the request fails.
        """
        # POST with basic auth        
        headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
        
        params = {**decisionInputs}
        if trace:
            params.update(self.trace)  # Add trace information to params

        try:
            path = '/rest'+rulesetPath
            session = self.runtime_credentials.get_session()
            response = session.post(self.runtime_credentials.odm_url+path, headers=session.headers, json=params)
            self.logger.info(f"{self.runtime_credentials.odm_url}{path} {response.status_code} {len(response.text)}")
        finally:
            self.runtime_credentials.cleanup()

        # check response
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            raise ToolError(f"Ruleset not found. The list of tools needs to be updated.")
        else:
            err = response.content.decode('utf-8')
            self.logger.error(f"Request error, status: {response.status_code}, error: {err}")
            raise Exception(err)
