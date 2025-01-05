import warnings

warnings.filterwarnings("ignore", message="Valid config keys have changed in V2:*")

import os
import subprocess
import tempfile
from typing import Optional
import platform
from pathlib import Path
import re

import click
from litellm import litellm
from promptic import llm
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.pretty import pprint
from rich.syntax import Syntax
from ruamel.yaml import YAML

__version__ = "0.7.7"

DEFAULT_VALUES = {
    "model": "gpt-4o",
    "api_key": None,
    "control": False,
    "attempts": 5,
    "ensure": False,
    "cleanup": False,
    "synchronous": False,
}

SYSTEM_PROMPT = """
You are an expert Python developer tasked with writing scripts to fulfill user instructions.
Your scripts should be concise, use modern Python idioms, and leverage appropriate libraries.

Key guidelines:
- Return complete, runnable Python scripts that use the necessary imports
- Prefer standard library solutions when appropriate
- Scripts should be self-contained and handle their own dependencies via uv
- Script should be as concise as possible while maintaining legibility
- All scripts should include proper uv script metadata headers with dependencies
- The script should be written such that it only succeeds if it achieves the goal or answers the user's query. Otherwise, it should fail.
- If successful, the script should print a message to stdout with all relevant information.

Important uv script format:
Scripts must start with metadata in TOML format:
```
# /// script
# dependencies = [
#    "package1>=1.0",
#    "package2<2.0"
# ]
# ///
```

This metadata allows uv to automatically create environments and manage dependencies.
The script will be executed using `uv run` which handles installing dependencies.

When fixing errors:
1. Carefully analyze any error messages or unexpected output
2. Make targeted fixes while maintaining the script's core functionality
3. Ensure all imports and dependencies are properly declared
4. Test edge cases and error conditions

Remember to handle common scenarios like:
- File and directory operations
- Process management
- Network requests
- System information gathering
- Error handling and user feedback

Focus on writing reliable, production-quality code that solves the user's needs efficiently.
"""

console = Console()

yaml = YAML()

config_path = Path.home() / ".config" / "skeet" / "config.yaml"

if config_path.exists():
    configurations = yaml.load(config_path)
else:
    configurations = {}


class ScriptResult(BaseModel):
    """Model for LLM response structure"""

    script: str
    message_to_user: str
    the_goal_was_attained: bool = False
    i_have_seen_the_last_terminal_output: bool = False


def stream_output(process, output_queue):
    """Stream output from a subprocess to a queue"""
    for line in iter(process.stdout.readline, ""):
        output_queue.put(line)
    process.stdout.close()


def run_script(script: str, cleanup: bool, verbose: bool) -> tuple[str, int, str]:
    """Run the given script using uv and return the output"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        with Status("[bold blue]Running script...", console=console):
            # Use Popen to stream output in real-time
            process = subprocess.Popen(
                ["uv", "run", "-q", script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Collect output while streaming it
            output_lines = []
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    output_lines.append(line)
                    if verbose:
                        console.print(line.rstrip())

            process.stdout.close()
            return_code = process.wait()

            return "".join(output_lines).strip(), return_code, script_path

    finally:
        if cleanup:
            # Clean up temporary file
            os.unlink(script_path)


@click.command()
@click.argument("instructions", nargs=-1, required=False)
@click.option(
    "--control",
    "-c",
    is_flag=True,
    help="Prompt for permission before each execution",
)
@click.option(
    "--model",
    "-m",
    envvar="SKEET_MODEL",
    help="Specify the LLM model to use",
)
@click.option(
    "--api-key",
    "-k",
    envvar="SKEET_API_KEY",
    help="API key for the LLM service",
)
@click.option(
    "--attempts",
    "-a",
    help="Maximum number of script execution attempts. If less than 0, the program will loop until the script is successful, regardless of errors.",
)
@click.option(
    "--ensure",
    "-e",
    is_flag=True,
    help="If true, the llm will check the output of the script and determine if the goal was met. By default, the program will terminate if the script returns a zero exit code.",
)
@click.option(
    "--cleanup",
    "-x",
    is_flag=True,
    help="If true, the program will clean up the temporary file after running the script.",
)
@click.option(
    "--upgrade",
    "-U",
    is_flag=True,
    help="Upgrade Skeet to the latest version with uv.",
)
@click.option(
    "--namespace",
    "-n",
    default="default",
    help="Specify the configuration namespace to use for the LLM model.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="If true, the program will print verbose output.",
)
@click.option(
    "--synchronous",
    "-s",
    is_flag=True,
    help="If true, the program will NOT stream the output of the script. It will run synchronously.",
)
@click.version_option(version=__version__)
def main(
    instructions: tuple,
    control: bool,
    model: Optional[str],
    api_key: Optional[str],
    attempts: int,
    ensure: bool,
    cleanup: bool,
    upgrade: bool,
    namespace: str,
    verbose: bool,
    synchronous: bool,
):
    """Describe what you want done, and Skeet will use AI to make it happen."""

    assert attempts != 0, "Attempts must be greater or less than 0"

    if upgrade:
        with Status("[bold yellow]Upgrading Skeet...", console=console):
            subprocess.run("uv tool install -P skeet skeet", shell=True)
        return

    if not instructions:
        ctx = click.get_current_context()
        click.echo(ctx.get_help())
        ctx.exit()

    if namespace not in configurations:
        raise ValueError(f"Namespace {namespace} not found in config.yaml")

    config = configurations[namespace]

    model = model or config.get("model", DEFAULT_VALUES["model"])
    api_key = api_key or config.get("api_key", DEFAULT_VALUES["api_key"])
    control = control or config.get("control", DEFAULT_VALUES["control"])
    attempts = attempts or config.get("attempts", DEFAULT_VALUES["attempts"])
    ensure = ensure or config.get("ensure", DEFAULT_VALUES["ensure"])
    cleanup = cleanup or config.get("cleanup", DEFAULT_VALUES["cleanup"])
    # if ensure is true, then we will run synchronously
    synchronous = (
        synchronous
        or ensure
        or config.get("synchronous", DEFAULT_VALUES["synchronous"])
    )

    if verbose:
        pprint(
            {
                "model": model,
                "api_key": api_key[:5] + "..." + api_key[-5:] if api_key else None,
                "control": control,
                "attempts": attempts,
                "ensure": ensure,
                "cleanup": cleanup,
                "synchronous": synchronous,
            }
        )

    @llm(
        system=SYSTEM_PROMPT,
        memory=True,
        model=model,
        stream=not synchronous,
        json_schema=ScriptResult.model_json_schema() if ensure else None,
    )
    def invoke_llm(
        goal: str,
        last_terminal_output: str = "",
        platform: str = platform.platform(),
    ):
        """Create or modify a Python script based on the goal, previous output, and platform.

        If last_terminal_output is provided, analyze it for errors and make necessary corrections.

        Goal: '{goal}'
        Last Output: ```{last_terminal_output}```
        Platform: {platform}
        """

    ensure_instructions = """
        Return the script along with whether you have seen the last terminal output, the goal was attained, and a message to the user.

        If Last Output is empty, meaning there is nothing within the triple backticks, i_have_seen_the_last_terminal_output is False.
        If the goal was attained and you have seen the last terminal output, the message_to_user should be a concise summary of the terminal output.
    """

    if ensure:
        invoke_llm.__doc__ += os.linesep + ensure_instructions
    if not synchronous:
        invoke_llm.__doc__ += os.linesep + "Enclose the script in triple backticks with python as the language."

    if api_key:
        litellm.api_key = api_key

    instruction_text = " ".join(instructions)

    last_output = None
    iteration = 0
    return_code = -1

    while attempts < 0 or iteration < attempts:
        iteration += 1

        if verbose:
            pprint({"iteration": iteration, "return_code": return_code})

        if return_code == 0 and not ensure:
            return

        def execute_llm() -> dict | str:
            invocation = invoke_llm(instruction_text, last_output)

            if synchronous:
                return invocation

            result = ""
            for chunk in invocation:
                if verbose or not ensure:
                    console.print(chunk, end="")
                result += chunk
            print()
            return result

        if ensure:
            with Status("[bold yellow]Communicating with LLM...", console=console):
                result = ScriptResult(**execute_llm())
        else:
            if synchronous:
                with Status("[bold yellow]Communicating with LLM...", console=console):
                    result_string = execute_llm()
            else:
                result_string = execute_llm()

            try:
                script = re.search(
                    r"```python\n(.*?)```", result_string, re.DOTALL
                ).group(1)
            except AttributeError:
                console.print("[yellow]Failed to extract script from output.[/yellow]")
                console.print(
                    Panel(result_string, title="LLM Output", border_style="yellow")
                )
                # assume the script is the result_string
                script = result_string

            result = ScriptResult(
                script=script,
                message_to_user="",
                the_goal_was_attained=False,
                i_have_seen_the_last_terminal_output=False,
            )

        if iteration == attempts:
            console.print("[red]Maximum iterations reached without success[/red]")
            return

        def display_result():
            console.print(
                Panel(
                    last_output,
                    title="Script Output",
                    subtitle=script_path if not cleanup else "",
                    border_style="green" if return_code == 0 else "red",
                )
            )

        if all(
            [
                result.i_have_seen_the_last_terminal_output,
                result.the_goal_was_attained,
                last_output,
                return_code == 0,
            ]
        ):
            if ensure:
                display_result()
            return

        if synchronous:
            console.print(Panel(Syntax(result.script, "python"), title="Script"))

        if control:
            changes = click.prompt(
                os.linesep
                + "What changes would you like to make to the script? Hit Enter to run without changes.",
                type=str,
                default="",
            )
            if changes:
                instruction_text = changes
                continue

        last_output, return_code, script_path = run_script(result.script, cleanup, verbose)

        if result.message_to_user and synchronous:
            console.print(Panel(result.message_to_user, title="LLM"))

        if not ensure:
            display_result()


if __name__ == "__main__":
    main()
