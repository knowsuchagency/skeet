# Skeet

Describe what you want done in your terminal, and *Skeet* will use AI to make it happen. 

Skeet works by leveraging [promptic](https://github.com/knowsuchagency/promptic) to generate Python scripts and `uv` to run them. By leveraging [uv scripts](https://docs.astral.sh/uv/guides/scripts/), Skeet can can execute Python scripts that have dependencies on third-party libraries without needing virtual environments.

<p align="center">
  <img src="https://github.com/user-attachments/assets/aaeddf6d-e9a0-4629-8a28-ef462029fba3" width="300" alt="logo">
</p>


## Examples

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

Skeet can be configured using a YAML file at `~/.config/skeet/config.yaml`.

None of the options are required, but `model` and `api_key` are recommended.

```yaml
model: "gpt-4" # Default LLM model to use
api_key: "sk-..." # Your LLM API key
control: false # Whether to prompt for permission before each execution
attempts: 5 # Maximum number of script execution attempts
ensure: false # Whether to verify script output with LLM
no_loop: false # Whether to run only once without retrying
```

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
