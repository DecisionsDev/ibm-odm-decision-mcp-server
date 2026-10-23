# IBM watsonx Orchestrate Integration Guide

## Overview

This page explains how to augment IBM watsonx Orchestrate with decisions implemented in IBM Operational Decision Manager (ODM), or in other words, how to enable watsonx Orchestrate to execute ODM rulesets during a user interaction in a chat.

This integration is possible thanks to the Decision MCP Server, and this page explains how to configure it in IBM watsonx orchestrate.

## Prerequisites

You need a running instance of both:
- [IBM watsonx Orchestrate](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base)
- IBM Operational Decision Manager

## Configuration

### 1. Create an agent

- Click the main menu icon

   ![main menu](images/wxo-main-menu.png)

- Navigate to **Build > Agent Builder**

   ![Build > Agent Builder](images/wxo-agent-builder.png)

- Navigate to **All agents**,
- Click **Create agent +** to add a new agent. 

   ![Create an agent](images/wxo-create-agent.png)

- Choose **Create from scratch**,
- Enter a **Name** eg. `ODM agent`
- Enter a **Description** eg. `This agent enables to execute ODM rulesets.`
- Click **Create**

   ![Create an agent (continued)](images/wxo-create-agent-2.png)

### 2. Augment the agent with an Decision MCP Server

- Navigate to the **Toolset** section, click **Add tool +**.

   ![Add tools +](images/wxo-add-tool.png)

- Click **Import**

   ![Import](images/wxo-import.png)

- Click **Import from MCP server**

   ![Import from MCP Server](images/wxo-import-from-mcp-server.png)

- Click **Add MCP server**

   ![Add MCP Server](images/wxo-add-mcp-server.png)

- Enter a **Server name** <u>without any space character</u> eg. `ODM_MCP_Server`
- Optionally enter a **Description** eg. `This MCP Server connects to an ODM Decision Server, enabling to execute the rulesets deployed.`
- Enter an **Install command** that starts the Decision MCP Server
   > Note 1:
   >  - `uvx --from <Decision_MCP_server_Source_Code_archive_URL> ibm-odm-decision-mcp-server`
   >  - where `<Decision_MCP_server_Source_Code_archive_URL>` should be replaced an URL such as:
   >
   >    | Type of archive | Example | URL |
   >    |-----------------|---------|-----|
   >    | Branch | `main` | `https://github.com/DecisionsDev/ibm-odm-decision-mcp-server/archive/refs/heads/main.zip` |
   >    | Tag | `v1.1.0.0` | `https://github.com/DecisionsDev/ibm-odm-decision-mcp-server/archive/refs/tags/v1.1.0.0.zip` |
   >    | Commit | `2cffad4` | `https://github.com/DecisionsDev/ibm-odm-decision-mcp-server/archive/2cffad4e161500e517eb733906c0c85dcca7097b.zip` |
   >
   >  - followed by :
   >    - `--url <RES_URL>` (where RES_URL is the URL of the ODM RES console where the rulesets to be used as tools are deployed)
   >    - authentication arguments to connect to the ODM RES console (either using basic auth, OpenId, or Zen Api Key)
   >  - For more about those arguments, please refer to [the main README.md (chapter 'ODM Container Environments & Authentication')](../README.md#1-odm-container-environments--authentication)

   > Note 2:
   >  - Before clicking **Connect**, make sure that the rulesets that should be exposed as tools through the Decision MCP Server, are deployed and configured accordingly using the ruleset parameter `agent.enabled` = `True`, otherwise you need to delete the MCP server and recreate it
   >  - you can deploy the rulesets provided as samples in [`samples`](/samples/). To do so:
   >    - either import [`samples-ruleapp.jar`](/samples/samples-ruleapp.jar) in the RES console directly
   >    - or import the Decision Services [`Beauty Advisory Service`](/samples/Beauty_Advisory_Service.zip) and [`Vacation Service`](/samples/Vacation_Service.zip) in Decision Center and deploy each to the RES console  

- Click **Connect**
- If you should see "Connection successful", click **Done**
- If not, try to modify the Install command and retry. You may need to delete the MCP server beforehand. To do so:
   - Click **Cancel** to go back to the previous step,
   - Click **Manage MCP servers**
   - Select your MCP server and click **Delete** in the menu icon

   ![Add MCP Server (continued)](images/wxo-add-mcp-server-2.png)

- set the **Activation toggle** to **On** for the tools (rulesets) to be enabled

   ![Enable tools](images/wxo-enable-tools.png)

### 3. Deploy the agent

- Click **Deploy**
![Configuration completed](images/wxo-deploy.png)

- In the popup, Click **Deploy** again
![Configuration completed](images/wxo-deploy-2.png)

### 4. Let the agent be used in chats

- Click the main menu icon

   ![main menu](images/wxo-main-menu.png)

- Navigate to **Chat**

   ![chat menu entry](images/wxo-menu-chat.png)

- Click the newly created agent

   ![select the agent](images/wxo-select-agent.png)


## Limitations and Workarounds

### Complex Types in Decision Service Signatures

**Limitation:** IBM watsonx Orchestrate currently does not support decision services that contain complex types (custom classes or complex objects) in their input/output signatures. Attempting to expose such decision services through the Decision MCP Server may result in integration issues or unexpected behavior.

**Workaround:** To ensure compatibility with watsonx Orchestrate, design your decision services to expose only simple types in their signatures. This can be achieved by:

1. **Flattening Data Type Definitions**  
   Instead of using complex custom types, break down the data structure into individual simple type parameters (strings, numbers, booleans, dates, etc.).

2. **Creating a Facade Decision Operation**  
   Users do **not** need to modify the core decision service or its complex parameters. Instead, create a new decision operation that acts as a facade:
   - Define a ruleset that uses only simple type parameters.
   - Implement a new ruleflow that maps these simple parameters to the original complex objects.
   - Call the main decision service ruleflow from this facade.

3. **Example Transformation**  
   - **Before (Complex Type):**
     ```
     Input: Customer (complex type with properties: name, age, address, creditScore)
     Output: LoanDecision (complex type with properties: approved, amount, rate)
     ```
   
   - **After (Facade with Simple Types):**
     ```
     Input: customerName (string), customerAge (number), customerAddress (string), customerCreditScore (number)
     Output: loanApproved (boolean), loanAmount (number), loanRate (number)
     ```
     The new ruleflow maps these simple inputs to the original `Customer` object and invokes the main decision service internally.

By following this approach, you ensure seamless integration between ODM decision services and watsonx Orchestrate while preserving the integrity of your existing business logic.


## Example of chat

- For instance, with the ruleset from `Vacation Service` deployed, you can have the following interaction in a chat:

   ![chat](images/wxo-chat.png)

- Click **Show Reasoning** to see the request sent to the ruleset and its response:

   ![chat reasoning](images/wxo-chat-reasoning.png)


## Help

For more about IBM Watsonx Orchestrate, see [Getting Started](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=getting-started-watsonx-orchestrate).
