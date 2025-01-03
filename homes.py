import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from pydantic import BaseModel
import tempfile
import os
import subprocess
from pathlib import Path
from typing import Optional
from promptic import llm
from litellm import litellm

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


def run_script(script: str, verbose: bool) -> tuple[str, int]:
    """Run the given script using uv and return the output"""
    if verbose:
        console.print(Panel(Syntax(script, "python"), title="Executing Script"))

    # Create temporary script file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        # Run script using uv
        result = subprocess.run(
            ["uv", "run", script_path], capture_output=True, text=True
        )
        output = result.stdout if result.returncode == 0 else f"Error:\n{result.stderr}"
    finally:
        # Clean up temporary file
        os.unlink(script_path)

    return output, result.returncode


@click.command()
@click.argument("instructions", nargs=-1, required=True)
@click.option(
    "--verbose", "-v", is_flag=True, help="Show detailed execution information"
)
@click.option(
    "--control", "-c", is_flag=True, help="Prompt for permission before each execution"
)
@click.option("--model", "-m", default="gpt-4o", help="Specify the LLM model to use")
@click.option("--api-key", help="API key for the LLM service")
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
        If the goal was attained and you have seen the last terminal output, the message_to_user should be a summary of the terminal output.
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

        if iteration == max_iterations:
            console.print("[red]Maximum iterations reached without success[/red]")
            return

        # Generate or update script
        result = invoke_llm(instruction_text, last_output)

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

        

        if control:
            console.print(
                Panel(Syntax(result.script, "python"), title="Proposed Script")
            )
            if not click.confirm("Execute this script?"):
                console.print("Execution cancelled")
                return

        # Run the script
        last_output, return_code = run_script(result.script, verbose)

        if verbose:
            console.print(Panel(last_output, title="Script Output"))

        console.print(Panel(result.message_to_user))

        


if __name__ == "__main__":
    main()
