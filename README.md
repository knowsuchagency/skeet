# Skeet 🎯

Master your machine: If you know English, _Skeet_ makes you a terminal wizard.

Like a skilled marksman who keeps shooting until they hit their target, _Skeet_ transforms your natural language instructions into precise shell commands or Python scripts, adapting and retrying automatically until the job is done.

Built on [promptic](https://github.com/knowsuchagency/promptic) and powered by [uv](https://github.com/astral-sh/uv), _Skeet_ can execute Python scripts with access to third-party libraries—no virtual environments needed. When a command fails, _Skeet_ analyzes the output and adjusts its approach, ensuring your goals are met.

_Skeet_ supports any LLM provider available through [LiteLLM](https://docs.litellm.ai/docs/providers), including OpenAI, Anthropic, Azure, local models, and many more!

## Examples

```bash
# Shell commands (default)
skeet show me system information about this computer
skeet what is using port 8000
skeet "what's size of my downloads folder?"

# Python scripts (using -p or --python flag)
skeet --python convert all html files in the current directory to pdf
skeet -p "how many stars for https://github.com/knowsuchagency/promptic?"
```

![skeet](https://github.com/user-attachments/assets/0d0e153e-fb64-47f4-908b-ac0388206c38)

## Installation

The recommended installation method is [uv](https://github.com/astral-sh/uv).

```bash
uv tool install skeet
```

## Configuration

Skeet can be configured using a YAML file at `~/.config/skeet/config.yaml`.

You can support multiple LLM providers by adding a namespace to your config. You can define any namespaces you want, but you **must** have a `default` namespace.

To see the full list of available LLM models, see the [LiteLLM documentation](https://docs.litellm.ai/docs/providers). Simply use the appropriate model name as the value for the `model` key.

There aren't any keys that are required for a given namespace, but `model` and `api_key` are recommended.

```yaml
default: # Default namespace
  model: "gpt-4o" # Default LLM model to use
  api_key: "sk-..." # Your LLM API key
  confirm: false # Whether to prompt for permission before each execution
  attempts: 5 # Maximum number of execution attempts
  verify: false # Whether to verify output with LLM
  cleanup: false # Whether to clean up temporary files
  synchronous: false # Whether to run in synchronous mode
  python: false # Whether to use Python scripts instead of shell commands

openai: # OpenAI-specific configuration
  model: "o1-mini"
  api_key: "sk-..."

anthropic: # Anthropic-specific configuration
  model: "claude-3-5-sonnet-20240620"
  api_key: "sk-..."

ollama: # Local Ollama configuration
  model: "ollama_chat/phi3:medium"
```

You can specify which configuration to use with the `--namespace` or `-n` flag:

```bash
skeet -n anthropic "what's the weather like?"
skeet --namespace openai "list files in the current directory"
```

If no namespace is specified, the `default` one will be used.

## How it Works

1. You provide natural language instructions
2. Skeet sends these instructions to an LLM with a specialized prompt
3. The LLM generates either:
   - A shell command (default)
   - A Python script (with --python flag)
4. Skeet executes the command or script
5. If the execution fails or doesn't achieve the goal, Skeet can retry with improvements based on the error output

## Features

- Natural language to shell command or Python script conversion
- Shell command execution for common tasks
- Python script execution with automatic dependency management using `uv`
- Interactive mode for command/script approval
- Error handling and automatic retry
- Configurable LLM models
- Rich terminal output with syntax highlighting

[![asciicast](https://asciinema.org/a/697033.svg)](https://asciinema.org/a/697033)

