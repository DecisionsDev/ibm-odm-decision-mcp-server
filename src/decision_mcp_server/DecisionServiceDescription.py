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

from mcp_types import Tool
class DecisionServiceDescription:
    """
    Represents a decision service description for a specific tool.
    This class encapsulates the metadata and tool description for a decision service.
    Attributes:
        tool_name (str): The name of the tool associated with the decision service.
        engine (str): The engine used for decision processing (default is "odm").
        rulesetPath (str): The path to the ruleset, constructed from the ruleset's ID.
        ruleset (dict): The ruleset metadata dictionary.
        tool_description (Tool): An object describing the tool, including its name, description, and input schema.

    Args:
        tool_name (str): The name of the tool.
        ruleset (dict): The ruleset metadata, must contain at least "id" and "description" keys.
        input_schema (dict): The schema describing the expected input for the tool.
    """
    def __init__(self, tool_name, ruleset, description, input_schema):
        self.tool_name = tool_name
        self.engine = "odm"
        self.description = description
        self.rulesetPath = "/" + str(ruleset["id"])
        self.ruleset = ruleset

        self.tool_description = Tool(
            name=tool_name,
            description=description,
            input_schema=input_schema,
        )

    def __eq__(self, other):
        if not isinstance(other, DecisionServiceDescription):
            return NotImplemented
        return (
                self.tool_description.name         == other.tool_description.name
            and self.tool_description.description  == other.tool_description.description
            and self.tool_description.input_schema == other.tool_description.input_schema
        )

   