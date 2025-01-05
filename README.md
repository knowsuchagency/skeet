# 🦅 Skeet 🎯

Describe what you want done, and _Skeet_ will make it happen.

Like a skilled skeet shooter, _Skeet_ takes your terminal commands and targets them with precision through AI.

_Skeet_ works by using [promptic](https://github.com/knowsuchagency/promptic) to generate Python scripts and `uv` to execute them. Through [uv scripts](https://docs.astral.sh/uv/guides/scripts/), _Skeet_ can use third-party libraries without virtual environments.

## Examples

[![asciicast](https://asciinema.org/a/697025.svg)](https://asciinema.org/a/697025)

```bash

skeet show me system information about this computer

skeet convert all the html files in the current directory to pdf

skeet what is using port 8000

skeet "what's the total size of ~/Downloads?"
```

## Installation

The recommended installation method is [uv](https://github.com/astral-sh/uv).

```bash
uv tool install skeet
```

## Configuration

Skeet can be configured using a YAML file at `~/.config/skeet/config.yaml`. The configuration now supports multiple namespaces for different LLM providers and configurations.

There aren't any keys that are required for a given namespace, but model and api_key are recommended.

```yaml
default: # Default namespace
  model: "gpt-4o" # Default LLM model to use
  api_key: "sk-..." # Your LLM API key
  control: false # Whether to prompt for permission before each execution
  attempts: 5 # Maximum number of script execution attempts
  ensure: false # Whether to verify script output with LLM
  cleanup: false # Whether to clean up temporary files
  synchronous: false # Whether to run in synchronous mode

openai: # OpenAI-specific configuration
  model: "o1-mini"
  api_key: "sk-..."

anthropic: # Anthropic-specific configuration
  model: "claude-3-sonnet"
  api_key: "sk-..."

ollama: # Local Ollama configuration
  model: "ollama_chat/phi3:medium"
```

You can specify which configuration to use with the `--namespace` or `-n` flag:

```bash
skeet -n anthropic "what's the weather like?"
skeet --namespace openai "list files in the current directory"
```

If no namespace is specified, the `default` configuration will be used.

## How it Works

1. You provide natural language instructions
2. Skeet sends these instructions to an LLM with a specialized prompt
3. The LLM generates a Python script to accomplish the task
4. Skeet executes the script using `uv run`
5. If the script fails or doesn't achieve the goal, Skeet can retry with improvements based on the error output

## Features

- Natural language to Python script conversion
- Automatic dependency management using `uv`
- Interactive mode for script approval
- Error handling and automatic retry
- Configurable LLM models
- Rich terminal output with syntax highlighting
