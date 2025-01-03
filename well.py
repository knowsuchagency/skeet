import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from pydantic import BaseModel, ConfigDict
import tempfile
import os
import subprocess
from pathlib import Path
from typing import Optional
from promptic import llm
from litellm import litellm
from rich.live import Live
from rich.status import Status
from rich.text import Text
import sys
from threading import Thread
from queue import Queue, Empty

console = Console()

SYSTEM_PROMPT = """
You are an expert Python developer tasked with writing scripts to fulfill user instructions.
Your scripts should be concise, use modern Python idioms, and leverage appropriate libraries.

Key guidelines:
- Return complete, runnable Python scripts that use the necessary imports
- Prefer standard library solutions when appropriate
- Include detailed error handling and user feedback
- Scripts should be self-contained and handle their own dependencies via uv
- All scripts should include proper uv script metadata headers with dependencies

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


def run_script(script: str, verbose: bool) -> tuple[str, int]:
    """Run the given script using uv and return the output"""
    if verbose:
        console.print(Panel(Syntax(script, "python"), title="Executing Script"))

    # Create temporary script file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        script_path = f.name

    output_lines = []
    try:
        with Status("[bold blue]Running script...", console=console) as status:
            # Run script using uv with pipe for streaming
            process = subprocess.Popen(
                ["uv", "run", script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Set up output streaming
            output_queue = Queue()
            output_thread = Thread(target=stream_output, args=(process, output_queue))
            output_thread.daemon = True
            output_thread.start()

            # Display output in real-time
            while True:
                # Check if process has finished
                if process.poll() is not None and output_queue.empty():
                    break

                # Get output from queue
                try:
                    line = output_queue.get_nowait()
                    output_lines.append(line)
                    status.update(
                        f"[bold blue]Running script...\n[white]{line.strip()}"
                    )
                except Empty:
                    continue

            output_thread.join()
            return_code = process.returncode

    finally:
        # Clean up temporary file
        os.unlink(script_path)

    output = "".join(output_lines)
    return output, return_code


@click.command()
@click.argument("instructions", nargs=-1, required=True)
@click.option(
    "--verbose", "-v", is_flag=True, help="Show detailed execution information"
)
@click.option(
    "--control", "-c", is_flag=True, help="Prompt for permission before each execution"
)
@click.option("--model", "-m", envvar="HOMES_MODEL", default="gpt-4o", help="Specify the LLM model to use")
@click.option("--api-key", envvar="HOMES_API_KEY", help="API key for the LLM service")
@click.option(
    "--max-iterations",
    "-i",
    default=5,
    help="Maximum number of script generation iterations",
)
def main(
    instructions: tuple,
    verbose: bool,
    control: bool,
    model: Optional[str],
    api_key: Optional[str],
    max_iterations: int,
):
    """Generate and run Python scripts based on natural language instructions"""

    @llm(
        system=SYSTEM_PROMPT,
        memory=True,
        model=model,
    )
    def invoke_llm(goal: str, last_terminal_output: str = "") -> ScriptResult:
        """Create or modify a Python script based on the goal and previous output.

        If last_terminal_output is provided, analyze it for errors and make necessary corrections.
        Return the script along with whether you have seen the last terminal output, the goal was attained, and a message to the user.


        Goal: '{goal}'
        Last Output: ```{last_terminal_output}```

        If Last Output is empty, meaning there is nothing within the triple backticks, i_have_seen_the_last_terminal_output is False.
        If the goal was attained and you have seen the last terminal output, the message_to_user should be a concise summary of the terminal output.
        """

    if api_key:
        litellm.api_key = api_key

    # Join instructions into a single string
    instruction_text = " ".join(instructions)

    last_output = None
    iteration = 0
    return_code = -1

    while iteration < max_iterations:
        iteration += 1

        with Status("[bold yellow]Communicating with LLM...", console=console):
            result = invoke_llm(instruction_text, last_output)

        if iteration == max_iterations:
            console.print("[red]Maximum iterations reached without success[/red]")
            return

        # Check if task is complete
        if all(
            [
                result.i_have_seen_the_last_terminal_output,
                result.the_goal_was_attained,
                last_output,
                return_code == 0,
            ]
        ):
            if verbose:
                console.print(f"[green]Success[/green]")
                print(result.message_to_user)
            else:
                console.print(last_output)
            break

        if verbose or control:
            console.print(
                Panel(Syntax(result.script, "python"), title="Proposed Script")
            )
        
        if control:
            
            if not click.confirm("Execute this script?"):
                console.print("Execution cancelled")
                return

        # Run the script
        last_output, return_code = run_script(result.script, verbose)

        console.print(Panel(last_output, title="Script Output"))

        console.print(Panel(result.message_to_user))


if __name__ == "__main__":
    main()
