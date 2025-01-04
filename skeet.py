import warnings

warnings.filterwarnings("ignore", message="Valid config keys have changed in V2:*")

import os
import subprocess
import tempfile
from typing import Optional
import platform
from pathlib import Path

import click
from litellm import litellm
from promptic import llm
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.syntax import Syntax
from ruamel.yaml import YAML


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
    config = yaml.load(config_path)
else:
    config = {}


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


def run_script(script: str, cleanup: bool) -> tuple[str, int, str]:
    """Run the given script using uv and return the output"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        with Status("[bold blue]Running script...", console=console) as status:
            # Run script using uv and capture output
            process = subprocess.run(
                ["uv", "run", "-q", script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )

            return process.stdout.strip() or "", process.returncode, script_path

    finally:
        if cleanup:
            # Clean up temporary file
            os.unlink(script_path)


@click.command()
@click.argument("instructions", nargs=-1, required=True)
@click.option(
    "--control",
    "-c",
    is_flag=True,
    default=config.get("control", False),
    help="Prompt for permission before each execution",
)
@click.option(
    "--model",
    "-m",
    envvar="SKEET_MODEL",
    default=config.get("model", "gpt-4o"),
    help="Specify the LLM model to use",
)
@click.option(
    "--api-key",
    "-k",
    envvar="SKEET_API_KEY",
    default=config.get("api_key", None),
    help="API key for the LLM service",
)
@click.option(
    "--attempts",
    "-a",
    envvar="SKEET_ATTEMPTS",
    default=config.get("attempts", 5),
    help="Maximum number of script execution attempts. If less than 0, the program will loop until the script is successful, regardless of errors.",
)
@click.option(
    "--ensure",
    "-e",
    is_flag=True,
    default=config.get("ensure", False),
    help="If true, the llm will check the output of the script and determine if the goal was met. By default, the program will terminate if the script returns a zero exit code.",
)
@click.option(
    "--no-loop",
    "-n",
    is_flag=True,
    default=config.get("no_loop", False),
    help="If true, the program will not loop and will only run once. By default, the program will keep running until the instructions are satisfied.",
)
@click.option(
    "--cleanup",
    "-x",
    is_flag=True,
    help="If true, the program will clean up the temporary file after running the script.",
)
def main(
    instructions: tuple,
    control: bool,
    model: Optional[str],
    api_key: Optional[str],
    attempts: int,
    ensure: bool,
    no_loop: bool,
    cleanup: bool,
):
    """Generate and run Python scripts based on natural language instructions"""

    assert attempts != 0, "Attempts must be greater or less than 0"

    @llm(
        system=SYSTEM_PROMPT,
        memory=True,
        model=model,
    )
    def invoke_llm(
        goal: str,
        last_terminal_output: str = "",
        platform: str = platform.platform(),
    ) -> ScriptResult:
        """Create or modify a Python script based on the goal and previous output.

        If last_terminal_output is provided, analyze it for errors and make necessary corrections.
        Return the script along with whether you have seen the last terminal output, the goal was attained, and a message to the user.


        Goal: '{goal}'
        Last Output: ```{last_terminal_output}```
        Platform: {platform}

        If Last Output is empty, meaning there is nothing within the triple backticks, i_have_seen_the_last_terminal_output is False.
        If the goal was attained and you have seen the last terminal output, the message_to_user should be a concise summary of the terminal output.
        """

    if api_key:
        litellm.api_key = api_key

    instruction_text = " ".join(instructions)

    last_output = None
    iteration = 0
    return_code = -1

    while attempts < 0 or iteration < attempts:
        iteration += 1

        if return_code == 0 and not ensure:
            return

        with Status("[bold yellow]Communicating with LLM...", console=console):
            result = invoke_llm(instruction_text, last_output)

        if iteration == attempts:
            console.print("[red]Maximum iterations reached without success[/red]")
            return

        if all(
            [
                result.i_have_seen_the_last_terminal_output,
                result.the_goal_was_attained,
                last_output,
                return_code == 0,
            ]
        ):
            return

        console.print(Panel(Syntax(result.script, "python"), title="Script"))

        if control:
            changes = click.prompt(
                "What changes would you like to make to the script? Hit Enter to run without changes.",
                type=str,
                default="",
            )
            if changes:
                instruction_text = changes
                continue

        last_output, return_code, script_path = run_script(result.script, cleanup)

        console.print(Panel(result.message_to_user, title="LLM"))

        console.print(
            Panel(
                last_output,
                title="Script Output",
                subtitle=script_path if not cleanup else "",
                border_style="green" if return_code == 0 else "red",
            )
        )

        if no_loop:
            break


if __name__ == "__main__":
    main()
