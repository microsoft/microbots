# MicrobotsLogAnalyzer Azure Pipelines Task

`MicrobotsLogAnalyzer` is an Azure DevOps custom task that runs Microbots `LogAnalysisBot` against a log file. It authenticates to Azure OpenAI through an Azure Resource Manager Service Connection, creates an isolated Python venv on the build agent, installs `microbots[azure_ad]`, and prints the root-cause analysis into the pipeline logs.

## Prerequisites

- Azure DevOps organization where you can install custom extensions.
- Azure Resource Manager Service Connection with permission to request tokens for the Azure OpenAI resource. The pipeline must be authorized to use this service connection.
- Azure Pipelines agent with `azure-cli`, `python3`, `pip` and `python3 -m venv` support.
- Azure OpenAI deployment that works with Microbots and is reachable by the service connection.
- Node.js on the machine where you package and publish the extension.

## Publish The Task

From a clone of this repository:

```bash
npm install -g tfx-cli

cd azure-pipelines/MicrobotsLogAnalyzerTask
npm ci --omit=dev

cd ..
tfx extension create --manifest-globs vss-extension.json
tfx extension publish --manifest-globs vss-extension.json --token <AZURE_DEVOPS_PAT> --share-with <AZURE_DEVOPS_ORGANIZATION>
```

Update the `publisher` value in `vss-extension.json` before running `tfx extension create`. The task folder must contain `node_modules` when the VSIX is created, so run `npm ci --omit=dev` before packaging.

After publishing, install the extension into the Azure DevOps organization that owns your pipelines.

When publishing an update, increment both versions before packaging:

- `azure-pipelines/vss-extension.json` controls the extension version.
- `azure-pipelines/MicrobotsLogAnalyzerTask/task.json` controls the task version shown to Azure Pipelines.

You can use `tfx extension create --manifest-globs vss-extension.json --rev-version` to increment the extension patch version, but task behavior changes still need a `task.json` version bump.

## Use It In A Pipeline

See the complete sample pipeline at [docs/examples/azure-pipelines/microbots-log-analyzer.yml](examples/azure-pipelines/microbots-log-analyzer.yml).

```yaml
- task: MicrobotsLogAnalyzer@0
  displayName: Analyze build log
  inputs:
    serviceConnection: my-azure-service-connection
    deploymentName: my-azure-openai-deployment
    endpoint: https://my-azure-openai-resource.openai.azure.com/
    apiVersion: 2025-03-01-preview
    codebasePath: $(Build.SourcesDirectory)
    logFilePath: logs/build.log
    timeoutSeconds: 600
    maxIterations: 20
```

The log file must exist before `MicrobotsLogAnalyzer@0` runs. Relative `logFilePath` values are resolved from `codebasePath`; absolute paths are also supported.

## Inputs

| Input | Required | Default | Description |
|---|---:|---|---|
| `serviceConnection` | Yes | - | Azure Resource Manager Service Connection used for Azure CLI login. |
| `deploymentName` | Yes | - | Azure OpenAI deployment name. |
| `endpoint` | Yes | - | Azure OpenAI endpoint, for example `https://my-resource.openai.azure.com/`. |
| `apiVersion` | Yes | - | Azure OpenAI API version passed to Microbots, for example `2025-03-01-preview`. |
| `codebasePath` | Yes | - | Repository or source folder Microbots can inspect while analyzing the log. |
| `logFilePath` | Yes | - | Log file path. Use an absolute path, or a relative path resolved from `codebasePath`. |
| `timeoutSeconds` | No | `600` | Maximum time for `LogAnalysisBot.run()`. |
| `maxIterations` | No | LogAnalysisBot default | Maximum number of Microbots iterations. Leave unset to use the default from `LogAnalysisBot.run()`. |

## How It Works

1. Azure Pipelines runs the task with the `Node20_1` task handler.
2. The task logs in with the supplied Azure Resource Manager Service Connection.
3. The task creates or reuses a virtual environment (`microbots-log-analyzer-venv`).
4. The task installs `microbots[azure_ad]` into that virtual environment.
5. A short Python runner creates `LogAnalysisBot` with `AzureCliCredential`, mounts `codebasePath` as context, passes `logFilePath`, optional `maxIterations`, and `timeoutSeconds` to `LogAnalysisBot.run()`, and prints the analysis result.

The task clears the Azure CLI account at the end of the run. Its task manifest also uses Azure Pipelines command restrictions so analyzed log content cannot set arbitrary pipeline variables.
