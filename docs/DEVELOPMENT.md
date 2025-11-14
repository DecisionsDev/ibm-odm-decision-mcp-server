
# Development Guide for ibm-odm-decision-mcp-server

This document contains instructions for building, publishing, and debugging the ibm-odm-decision-mcp-server MCP server.

## Prerequisite

Here is the requirement to contriube to the code
   * [Rancher](https://rancherdesktop.io/) or a Docker equivalent implementation
   * Python 3.11 or higher
   * [uv](https://docs.astral.sh/uv/getting-started/installation/)
   * [NodeJS/NPX](https://nodejs.org/en) (On mac `brew install node`)
     
## Setup ODM 

To develop localy you can use the ODM for Developer image.

This allow you to test the connection between the MCP Server and ODM localy.
```bash
docker run -d -p 9060:9060 -e SAMPLE=true -e LICENSE=accept --name odm docker.io/ibmcom/odm:9.5.0.0_25.0.0
```
You can find a ruleapp in the directory  [samples/samples-ruleapp.jar](/samples/samples-ruleapp.jar) that you can use for the test.



## Developping the code

git clone the repository
```bash
git clone git@github.com:DecisionsDev/ibm-odm-decision-mcp-server.git
```

or

```bash
git clone https://github.com/DecisionsDev/ibm-odm-decision-mcp-server.git
```

Then you can run the MCP server as show in the next section Debugging.


## Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging experience, we strongly recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).

You can launch the MCP Inspector via [`npm`](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) with this command:

```bash
npx @modelcontextprotocol/inspector uv run ibm-odm-decision-mcp-server
```

Upon launching, the Inspector will display a URL that you can access in your browser to begin debugging.

Then you can click to the tools tab and list tools. This should list the tools available in the Decision Server console.
 
## Building and Publishing

To prepare the package for distribution:

1. Sync dependencies and update lockfile:
```bash
uv sync
```

2. Build package distributions:
```bash
uv build
```
This will create source and wheel distributions in the `dist/` directory.

3. Publish to PyPI:
```bash
uv publish
```

Note: You'll need to set PyPI credentials via environment variables or command flags:
- Token: `--token` or `UV_PUBLISH_TOKEN`
- Or username/password: `--username`/`UV_PUBLISH_USERNAME` and `--password`/`UV_PUBLISH_PASSWORD`

