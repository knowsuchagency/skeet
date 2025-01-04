# Skeet

Skeet is a command-line tool that generates and executes Python scripts using natural language instructions through LLM integration. It allows you to describe what you want to accomplish, and Skeet will create and run the appropriate Python script.

## Examples

```bash
skeet list all python files here

skeet show me system information about this computer

skeet what is using port 8000

skeet "what's the total size of the current directory?"
```

## Installation

The recommended installation method is using [uv](https://github.com/astral-sh/uv).

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
