# IBM ODM Decision MCP Server Documentation

## Overview

The IBM ODM Decision MCP Server bridges IBM ODM with modern AI assistants and orchestration platforms.  
It enables you to:
- Expose decisions as tools for AI assistants
- Automate decisions dynamically in workflows
- Integrate easily with Watson Orchestrate, Claude Desktop, and Cursor AI
- Centralize and expose business logic to end users and bots

---

## Features

- **Tool Integration:** Add and invoke ODM decisions (aka rulesets) as tools
- **Decision Storage:** Manage resources with a local storage system
- **Authentication:** Zen API Key, Basic Auth, and OpenID Connect
- **Multi-Platform:** Works with Watson Orchestrate, Claude Desktop, and Cursor AI

---

## Quickstart: Claude Desktop Integration

For detailed instructions on setting up and using Claude Desktop with the Decision MCP Server, see the [Claude Desktop Integration Guide](/docs/Claude-desktop-integration-guide.md).

### Demo Video

Watch our demo video to see Claude Desktop integration in action:

![](https://github.com/user-attachments/assets/3fce0475-e2a3-491f-9f88-9ae71f52d410)


## IBM Watsonx Orchestrate Integration

IBM watsonx Orchestrate can be augmented with decisions implemented in IBM Operational Decision Manager (ODM) thanks to the Decision MCP Server.

For detailed instructions, see the [IBM watsonx Orchestrate Integration Guide](/docs/IBM-watsonx-orchestrate-guide.md).


---

## Prerequisites & Installation

### Prerequisites

- **Python 3.13 or higher** - This MCP server is written in Python and requires Python 3.13+
- **uv** - A fast Python package installer and resolver (recommended)

### Installing uv

The easiest way to run the Decision MCP Server is using `uv`, which handles package installation and execution:

**macOS and Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Alternative (via pip):**
```bash
pip install uv
```

For more installation options, see the [uv documentation](https://docs.astral.sh/uv/getting-started/installation/).

### Running the Server

Once `uv` is installed, you can run the Decision MCP Server directly without manual installation:

```bash
uvx --from git+https://github.com/DecisionsDev/ibm-odm-decision-mcp-server ibm-odm-decision-mcp-server --url http://localhost:9060/res
```

The `uvx` command automatically:
- Downloads and installs the package
- Manages dependencies
- Runs the server

---
## Configuration

### 1. ODM Container Environments & Authentication

Depending on your IBM ODM deployment, use the appropriate authentication/authorization method:

#### 1.1. **ODM on Cloud Pak for Business Automation**
- **Environment:** Cloud Pak for Business Automation (CP4BA)
- **Authentication:** Zen API Key
  - **CLI:** `--zenapikey <your-zen-api-key>`
  - **Env:** `ZENAPIKEY=<your-zen-api-key>`

#### 1.2. **ODM on Kubernetes**
- **Environment:** IBM ODM deployed on Kubernetes (including OpenShift)
- **Authentication:**  
  - **Basic Auth:**  
    - **CLI:** `--username <user> --password <pass>`
    - **Env:** `ODM_USERNAME=<user> ODM_PASSWORD=<pass>`
  - **OpenID Connect (using Client Secret):**
    - **CLI:** `--client-id <CLIENT_ID> --client-secret <CLIENT_SECRET> --token-url <TOKEN_URL>` and optionally `--scope <scope>`
    - **Env:** `CLIENT_ID=<client_id> CLIENT_SECRET=<client_secret> TOKEN_URL=<URL>` and optionally `SCOPE=<scope>`
  - **OpenID Connect (using Private Key JWT):**
    - **CLI:** `--client-id <CLIENT_ID> --pkjwt-key-path <PRIVATE_KEY_PATH> --pkjwt-cert-path <CERT_PATH> --token-url <TOKEN_URL>` and optionally `--scope <scope>` and `--pkjwt-key-password <PASSWORD>` if the private key is password-protected.
    - **Env:** `CLIENT_ID=<client_id> PKJWT_KEY_PATH=<private_key_path> PKJWT_CERT_PATH=<cert_path> TOKEN_URL=<URL>` and optionally `SCOPE=<scope>` and `PKJWT_KEY_PASSWORD=<password>` if the private key is password-protected.
    >**Note:** Both a private key and its certificate are required for PKJWT authentication. The private key is used for signing the JWT (Json Web Token), while the certificate is used for computing the x5t thumbprint. A password-protected private key can be used. In that case, the password must be specified.

#### 1.3. **ODM for Developers (Docker/Local)**
- **Environment:** Local Docker or Developer Edition
- **Authentication:** Basic Auth
  - **CLI:** `--username <user> --password <pass>`
  - **Env:** `ODM_USERNAME=<user> ODM_PASSWORD=<pass>`

### 2. Different authentication types: Console vs Runtime

The Decision MCP Server actually communicates with two different ODM components/servers:
- the RES console
- the Decision Server Runtime

When these two ODM components are configured to use different authentication types, the Decision MCP Server can be configured accordingly by:
- specifying all the parameters required to authenticate to both ODM components,
- and using the additional parameters below:
  - **CLI:** `--console-auth-type <console_auth_type> --runtime-auth-type <runtime_auth_type>`
  - **Env:** `CONSOLE_AUTH_TYPE=<console_auth_type> RUNTIME_AUTH_TYPE=<runtime_auth_type>`

    > where `<console_auth_type>` and `<runtime_auth_type>` must take one of the values below:
    > | auth_type | Description.                                             |
    > | ----------|--------------------------------------------------------- |
    > | BASIC     | basic authentication                                     |
    > | ZEN       | Zen API Key authentication.                              |
    > | SECRET    | OpenID Connect authentication with a Client Secret       |
    > | PKJWT     | OpenID Connect authentication with a Private Key (PKJWT) |
    > | NONE      | No authentication/authorization                          |

> Note: 
> - Decision MCP Server does not support to use the same authentication type with different credentials
> - for instance, Basic Auth with two different usernames (one for the RES console, and one for the Runtime)
> - This is not supported.
> - The unique user/service account must be configured to have access to both ODM components (see [3. Authorization](#3-authorization) below).

### 3. Authorization

#### 3.1. ODM on Cloud Pak for Business Automation

If ODM is deployed in IBM Cloud Pak for Business Automation, the user/service account used must have a role assigned that grants the Zen permissions below in order to be able to access both the RES Console and the Decision Server Runtime:

  | Zen permissions |
  |-----------------|
  | ODM - Monitor decision services in Decision Server |
  | ODM - Execute decision services in Decision Server |

Read more in [Managing user permissions](https://www.ibm.com/docs/en/cloud-paks/cp-biz-automation/25.0.0?topic=access-managing-user-permissions).

#### 3.2. ODM on Kubernetes

If ODM is deployed on Kubernetes, the user/service account used must have the roles below:

  | ODM roles     |
  |---------------|
  | resMonitors   |
  | resExecutors  |

#### 3.3. ODM on Cloud

If ODM is deployed in the managed offering ODM on Cloud, the role below must be assigned to the user/service account used (for the suitable environment (Development / Test / Production)):

  | ODM on Cloud role |
  |-------------------|
  | Monitor           |

Read more in [Creating and managing service accounts](https://www.ibm.com/docs/en/dbaoc?topic=access-creating-managing-service-accounts).


### 4. Secure connection

#### 4.1. Server certificate

To establish a SSL/TLS secure connection to the server, the Decision MCP server must have access to the certificate used to sign the server certificate.

If a public CA certificate was used to sign the server certificate, the Decision MCP server can find it among the system trusted certificates.

If this is a self-signed certificate, it can be specified :
  - **CLI:** `--ssl-cert-path <certificate_filename>`
  - **Env:** `SSL_CERT_PATH=<certificate_filename>`

Alternatively, in dev/test environments, the authenticity of the server can be ignored:
  - **CLI:** `--verifyssl "False"`
  - **Env:** `VERIFY_SSL="False"`

#### 4.2. mTLS (mutual TLS)

The server can be configured to check the authenticity of the clients that try to establish a secure connection.

In that case, the Decision MCP server (which acts as a client), must be configured with both a private key and its related certificate (and the server must be configured to trust the clients presenting that certificate when establishing a secure connection).

The parameters below can be specified:
  - **CLI:** `--mtls-key-path <PRIVATE_KEY_PATH> --mtls-cert-path <CERT_PATH>` and optionally `--mtls-key-password <PASSWORD>` if the private key is password-protected.
  - **Env:** `MTLS_KEY_PATH=<private_key_path> MTLS_CERT_PATH=<cert_path>` and optionally `MTLS_KEY_PASSWORD=<password>` if the private key is password-protected.



---

### Configuration Parameters Table

| CLI Argument      | Environment Variable | Description                                                                                            | Default                                 |
|-------------------|---------------------|---------------------------------------------------------------------------------------------------------|-----------------------------------------|
| `--url`           | `ODM_URL`           | URL of the Decision Server console (used for management and deployment operations)                      | `http://localhost:9060/res`             |
| `--runtime-url`   | `ODM_RUNTIME_URL`   | URL of the Decision Server runtime (used for executing decision services)                               | `<ODM_URL>/DecisionService`             |
| `--username`      | `ODM_USERNAME`      | Username for Basic Auth or Zen authentication                                                           | `odmAdmin`                              |
| `--password`      | `ODM_PASSWORD`      | Password for Basic Auth                                                                                 | `odmAdmin`                              |
| `--zenapikey`     | `ZENAPIKEY`         | Zen API Key for authentication with Cloud Pak for Business Automation                                   |                                         |
| `--client-id`     | `CLIENT_ID`         | OpenID Connect client ID for authentication                                                             |                                         |
| `--client-secret` | `CLIENT_SECRET`     | OpenID Connect client secret for authentication                                                         |                                         |
| `--pkjwt-cert-path` | `PKJWT_CERT_PATH` | Path to the certificate for PKJWT authentication (mandatory for PKJWT)                                  |                                         |
| `--pkjwt-key-path` | `PKJWT_KEY_PATH`   | Path to the private key certificate for PKJWT authentication (mandatory for PKJWT)                      |                                         |
| `--pkjwt-key-password` | `PKJWT_KEY_PASSWORD` | Password to decrypt the private key for PKJWT authentication. Only needed if the key is password-protected. |                               |
| `--token-url`     | `TOKEN_URL`         | OpenID Connect token endpoint URL for authentication                                                    |                                         |
| `--scope`         | `SCOPE`             | OpenID Connect scope used when requesting an access token using Client Credentials for authentication   | `openid`                                |
| `--verifyssl`     | `VERIFY_SSL`        | Whether to verify SSL certificates (`True` or `False`)                                                  | `True`                                  |
| `--ssl-cert-path` | `SSL_CERT_PATH`     | Path to the SSL certificate file. If not provided, defaults to system certificates.                     |                                         |
| `--mtls-cert-path`| `MTLS_CERT_PATH`    | Path to the SSL certificate file of the client for mutual TLS authentication (mandatory for mTLS)       |                                         |
| `--mtls-key-path` | `MTLS_KEY_PATH`     | Path to the SSL private key file of the client for mutual TLS authentication (mandatory for mTLS)       |                                         |
| `--mtls-key-password` | `MTLS_KEY_PASSWORD` | Password to decrypt the private key of the client for mutual TLS authentication. Only needed if the key is password-protected. |              |
| `--console-auth-type` | `CONSOLE_AUTH_TYPE` | Explicitly set the authentication type for the RES console (`BASIC`, `ZEN`, `PKJWT`, `SECRET`, `NONE`)      |                                 |
| `--runtime-auth-type` | `RUNTIME_AUTH_TYPE` | Explicitly set the authentication type for the Decision Server Runtime (`BASIC`, `ZEN`, `PKJWT`, `SECRET`, `NONE`) |                          |
| `--log-level`     | `LOG_LEVEL`         | Set the logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)                                 | `INFO`                                  |
| `--traces-dir`    | `TRACES_DIR`        | Directory to store execution traces                                                                     | `~/.mcp-server/traces`                  |
| `--trace-enable`  | `TRACE_ENABLE`      | Enable or disable trace storage (`True` or `False`)                                                     | `False`                                 |
| `--trace-maxsize` | `TRACE_MAXSIZE`     | Maximum number of traces to store before removing oldest traces                                         | `50`                                    |
          
### Decision MCP Server Configuration File          

You can configure the MCP server for clients like Claude Desktop or Cursor AI using a JSON configuration file, which can contain both environment variables and command-line arguments.

**Tips:**
- Use CLI arguments for quick overrides or non-sensitive parameters.
- Use environment variables for secrets.
- You can mix both methods if needed. CLI arguments override environment variables.

The example below shows a typical use-case where the sensitive information (here the password) is passed as an environment variable (so that it does not show in the arguments of the process), and the other parameters are passed as CLI arguments:

```json
{
  "mcpServers": {
    "ibm-odm-decision-mcp-server": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/DecisionsDev/ibm-odm-decision-mcp-server",
        "ibm-odm-decision-mcp-server",
        "--url", "https://odm-res-console-url",
        "--ssl-cert-path", "certificate-file",
        "--username", "your-username"
      ],
      "env": {
        "ODM_PASSWORD": "odmAdmin"
      }
    }
  }
}
```

The examples below demonstrate various use cases depending on the type of deployment (dev/test or production), and environments (CloudPak, ...).

---
#### Example 1: Basic Auth for Local Development

For local development and testing, use the Basic Auth.

```json
"args": [
  "--from",
  "git+https://github.com/DecisionsDev/ibm-odm-decision-mcp-server",
  "ibm-odm-decision-mcp-server",
  "--url", "http://localhost:9060/res",
  "--username", "odmAdmin"
],
"env": {
  "ODM_PASSWORD": "odmAdmin"
}
```

---
#### Example 2: For Cloud Pak (Zen API Key)

For production deployments on the Cloud Pak, use the Zen API Key.

```json
"args": [
  "--from",
  "git+https://github.com/DecisionsDev/ibm-odm-decision-mcp-server",
  "ibm-odm-decision-mcp-server",
  "--url",           "https://odm-res-console-url",
  "--ssl-cert-path", "certificate-file",
  "--username",      "YOUR_ZENUSERNAME"
],
"env": {
  "ZENAPIKEY": "YOUR_ZEN_API_KEY"
}
```

---
#### Example 3: OpenID Connect

For production deployments on other environments than the Cloud Pak, you may use OpenID Connect if ODM is configured to use it.

The Decision MCP Server can authenticate to ODM configured with OpenID Connect, using the Client Credentials flow.

Two authentication variants are possible:

1) Using a Client Secret
```json
"args": [
  "--from",
  "git+https://github.com/DecisionsDev/ibm-odm-decision-mcp-server",
  "ibm-odm-decision-mcp-server",
  "--url",           "https://odm-res-console-url",
  "--runtime-url",   "https://odm-runtime-url",
  "--ssl-cert-path", "certificate-file",
  "--token-url",     "https://your-openid-connect_provider-token-endpoint-url",
  "--scope",         "the_scope_to_be_used_for_client_credentials"
],
"env": {
  "CLIENT_ID":      "YOUR_CLIENT_ID",
  "CLIENT_SECRET":  "YOUR_CLIENT_SECRET"
}
```

2) Using a Private Key (PKJWT)
```json
"args": [
  "--from",
  "git+https://github.com/DecisionsDev/ibm-odm-decision-mcp-server",
  "ibm-odm-decision-mcp-server",
  "--url",           "https://odm-res-console-url",
  "--runtime-url",   "https://odm-runtime-url",
  "--ssl-cert-path", "certificate-file",
  "--token-url",     "https://your-openid-connect_provider-token-endpoint-url",
  "--scope",         "the_scope_to_be_used_for_client_credentials"
],
"env": {
  "CLIENT_ID":       "YOUR_CLIENT_ID",
  "PKJWT_KEY_PATH":  "PKJWT_PRIVATE_KEY_FILENAME",
  "PKJWT_CERT_PATH": "PKJWT_CERTIFICATE_FILENAME"
}
```

---
#### Example 4: mTLS (Mutual TLS) Authentication

The Decision MCP Server also supports mTLS (mutual TLS) authentication, which secure the SSL connection further.

When authorization is required (to assess the right to access to the service (RES console and/or Decision Service Runtime)), mTLS must be complemented with another means of authentication/authorization, for instance with basic auth in the example below:

```json
"args": [
  "--from",
  "git+https://github.com/DecisionsDev/ibm-odm-decision-mcp-server",
  "ibm-odm-decision-mcp-server",
  "--url",           "https://odm-res-console-url",
  "--runtime-url",   "https://odm-runtime-url",
  "--ssl-cert-path", "certificate-file",
  "--username",      "SERVICE_ACCOUNT"
],
"env": {
  "PASSWORD":       "SERVICE_ACCOUNT_PASSWORD",
  "MTLS_KEY_PATH":  "MTLS_PRIVATE_KEY_FILENAME",
  "MTLS_CERT_PATH": "MTLS_CERTIFICATE_FILENAME"
}
```

---
#### Example 5: Different Authentication Types: Console vs Runtime

The example below shows how to configure the Decision MCP Server when:
- the RES console uses OpenID Connect with PKJWT, and
- the Decision Server Runtime has been configured to use mTLS and have the authorization disabled

```json
"args": [
  "--from",
  "git+https://github.com/DecisionsDev/ibm-odm-decision-mcp-server",
  "ibm-odm-decision-mcp-server",
  "--url",           "https://odm-res-console-url",
  "--runtime-url",   "https://odm-runtime-url",
  "--ssl-cert-path", "certificate-file",

  "--console-auth-type", "PKJWT",
  "--token-url",         "https://your-openid-connect_provider-token-endpoint-url",
  "--scope",             "the_scope_to_be_used_for_client_credentials",

  "--runtime-auth-type", "NONE"
],
"env": {
  "CLIENT_ID":       "YOUR_CLIENT_ID",
  "PKJWT_KEY_PATH":  "PKJWT_PRIVATE_KEY_FILENAME",
  "PKJWT_CERT_PATH": "PKJWT_CERTIFICATE_FILENAME",

  "MTLS_KEY_PATH":   "PRIVATE_KEY_FILENAME",
  "MTLS_CERT_PATH":  "CERTIFICATE_FILENAME"
}
```

---

### Ruleset Properties for the Decision MCP Server

You can configure how your Decision Server rulesets are exposed as MCP tools by setting specific ruleset properties in IBM ODM. These properties control whether a ruleset is available as a tool and how it's presented to AI assistants.

#### Adding Ruleset Properties

You can add ruleset properties using any of these methods:

1. **In Rule Designer:**
   - Open your ruleset project
   - Right-click on the ruleset > Properties > Ruleset Properties
   - Add the desired properties with their values
   - Save and deploy your ruleset

2. **In Decision Center:**
   - Open the ruleset > Settings > Properties
   - Add the desired properties with their values
   - Save and deploy your ruleset

3. **In Decision Server Console:**
   - Log in to the Decision Server Console
   - Navigate to Explorer > Rulesets
   - Select your ruleset
   - Click on the "Properties" tab
   - Add the desired properties with their values
   - Click "Save"

#### MCP Configuration Properties
Property | Description | Default |
|-------------------|--------------------------------------------------------------------------|------------------------------------------|
`agent.enabled`     | Controls whether the ruleset is exposed as an MCP tool                   | `false`                                  |
`agent.name`        | Customizes the name of the tool as exposed to AI assistants              | Name of the decision operation. Display Name in the Decision Server console. |
`agent.description` | Overrides the default description of the ruleset when exposed as a tool  | Description of the decision operation     |

#### Example

```
agent.enabled=true
agent.description=This tool calculates vacation days based on employee tenure and position
```

**Note:** After updating ruleset properties, you need to redeploy the ruleset for changes to take effect.

---

### Fine-Tuning Tool Descriptions for LLMs

When exposing decision services as tools for LLMs, the quality of the tool descriptions significantly impacts how effectively the LLM can utilize them. Here are best practices for optimizing your tool descriptions:

#### Detailed Service Descriptions

Having detailed descriptions of what a service does and the expected parameter values can guide the LLM to be more precise when triggering tools.

##### Example:

```
Allow to compute the beauty advise. This takes as parameters:
- age: should be between 0 and 110
- sex: Value should be Male or Female
- skin color: should be one of these values: Dark, Ebony, Ivory, Light, Medium or Unknown
- hair color: should be one of these values: Black, Blonde, Brown, Gray, Red, White or Unknown

For the hair color or skin color, you can suggest possible values.
```

This detailed description helps the LLM understand:
- The purpose of the service ("compute beauty advice")
- Valid parameter ranges and constraints
- Acceptable enumeration values
- Guidance on how to handle certain parameters

#### Enhancing OpenAPI with Swagger Annotations

When service descriptions alone aren't sufficient to fully describe the API signature, you can augment your OpenAPI generation by adding Swagger annotations to your Java classes:

```java
package miniloan;

import io.swagger.v3.oas.annotations.media.Schema;

/**
 * This class models a borrower.
 * A borrower is created with a name, a credit score, and a yearly income.
 */
@Schema(description = "This class models a borrower. A borrower is created with a name, a credit score, and a yearly income.")
public class Borrower {
    @Schema(description = "The name of the borrower.")
    private String name;
    
    @Schema(description = "The credit score of the borrower.", format = "int32")
    private int creditScore;
    
    @Schema(description = "The yearly income of the borrower.", format = "int32")
    private int yearlyIncome;

    
    public Borrower() {
    }
}
```

These annotations provide:
- Detailed descriptions for each field
- Format specifications
- Additional metadata that can be included in the generated OpenAPI specification

> **Note:** It is not necessary to package the Swagger JAR file in the XOM (Execution Object Model) as it is already part of the IBM ODM product. You can use the annotations directly without adding additional dependencies to your project.

By combining rich service descriptions with properly annotated model classes, you can create tool definitions that LLMs can understand and use with high precision, reducing errors and improving the quality of interactions.

## More information

- For IBM Operational Decision Manager (ODM), see [IBM Documentation](https://www.ibm.com/docs/en/odm).
- For IBM Watsonx Orchestrate, see [Getting Started](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/base?topic=getting-started-watsonx-orchestrate).
- For Claude Desktop, see [Claude Documentation](https://claude.ai/docs).

---

## Development Checklist

- [x] Add sample scenario in the documentation - On going
- [x] Put in place intensive unit-tests with Coverage
- [x] Investigate XOM annotation
- [x] Investigate How to inject description from Decision Center
- [x] Store and expose Decision Trace executions as MCP resources
- [x] Manage ODM certificate
- [ ] Declare Structured Output
- [x] Decide naming convention prefix for Ruleset properties. (tools -> agent/decisionassistant )
- [x] Verify OpenID Connect authentication
- [ ] Expose a tool to explain decisions
- [x] Record demo video for Claude Desktop integration
- [x] Add a docker-compose to inject to deploy the ruleapps.
- [x] Support configuration via CLI and environment variables
- [x] Verify Zen authentication support
- [x] Support multiple Decision Server endpoints
- [x] Test and document Claude Desktop integration
- [x] Test  Cursor AI integration
- [ ] Implement Notification Context
- [ ] Support Remote MCP Server standard
