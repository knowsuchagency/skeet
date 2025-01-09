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
from rich.prompt import Prompt
from ruamel.yaml import YAML

__version__ = "2.2.4"

DEFAULT_VALUES = {
    "model": "gpt-4o",
    "api_key": None,
    "yolo": False,
    "attempts": 5,
    "verify": False,
    "cleanup": False,
    "synchronous": False,
    "python": False,
}

COMMAND_SYSTEM_PROMPT = """
You are an expert system administrator tasked with creating shell commands to fulfill the user's queries.
Your commands should be concise, use appropriate flags/options, and handle paths and special characters safely.

Focus on:
- Using the most appropriate command-line tools for each task
- Platform-specific considerations (Windows vs Unix)
- Proper error handling and user feedback
- Security best practices
- You cannot use `sudo`
"""

PYTHON_SYSTEM_PROMPT = """
You are an expert Python developer tasked with writing scripts to fulfill user's queries.
Your scripts should be concise, use modern Python idioms, and leverage appropriate libraries.

Key guidelines:
- Return complete, runnable Python scripts that use the necessary imports
- Prefer standard library solutions when appropriate
- Scripts should be self-contained and handle their own dependencies via uv
- Script should be as concise as possible while maintaining legibility
- All scripts should include proper uv script metadata headers with dependencies
- The script should be written such that it only succeeds if it satisfies the user's query. Otherwise, it should fail.
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


class Result(BaseModel):
    """Model for LLM response structure"""

    command_or_script: str
    message_to_user: str
    the_query_was_satisfied: bool = False
    i_have_seen_the_last_terminal_output: bool = False

    def __init__(self, **data):
        # Clean up any backticks from command_or_script before initialization
        # Deepseek occasionally adds them for some reason
        if "command_or_script" in data:
            data["command_or_script"] = (
                data["command_or_script"].replace("```", "").strip().strip("`")
            )
        super().__init__(**data)


def stream_output(process, output_queue):
    """Stream output from a subprocess to a queue"""
    for line in iter(process.stdout.readline, ""):
        output_queue.put(line)
    process.stdout.close()


def run_command(command: str, verbose: bool) -> tuple[str, int]:
    """Run the given command and return the output"""
    with Status("[bold blue]Running command...", console=console):
        process = subprocess.Popen(
            command,
            shell=True,
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

        return "".join(output_lines).strip(), return_code


def run_script(script: str, cleanup: bool, verbose: bool) -> tuple[str, int, str]:
    """Run the given script using uv and return the output"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        with Status("[bold blue]Running script...", console=console):
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


def get_shell_info():
    """Get information about the current shell environment"""
    if platform.system() == "Windows":
        shell = os.environ.get("COMSPEC", "cmd.exe")
        return "cmd.exe" if "cmd.exe" in shell.lower() else "powershell"
    return os.environ.get("SHELL", "bash").split("/")[-1]


@click.command()
@click.argument("query", nargs=-1, required=False)
@click.option(
    "--yolo",
    "-y",
    is_flag=True,
    help="Automatically execute scripts and commands without asking for confirmation.",
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
    "--verify",
    "-e",
    is_flag=True,
    help="If true, the llm will verify the query was satisfied. By default, the program will terminate if the script or command returns a zero exit code.",
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
    count=True,
    help="Increase verbosity level. Can be used multiple times (-v, -vv, -vvv).",
)
@click.option(
    "--synchronous",
    "-s",
    is_flag=True,
    help="If true, the program will NOT stream the output of the script -- it will run synchronously. This is the default behavior EXCEPT when using python.",
)
@click.option(
    "--python",
    "-p",
    is_flag=True,
    help="If true, the program will use Python to satisfy your query.",
)
@click.version_option(version=__version__)
def main(
    query: tuple,
    yolo: bool,
    model: Optional[str],
    api_key: Optional[str],
    attempts: int,
    verify: bool,
    cleanup: bool,
    upgrade: bool,
    namespace: str,
    verbose: int,
    synchronous: bool,
    python: bool,
):
    """Describe what you want done, and Skeet will use AI to make it happen."""

    assert attempts != 0, "Attempts must be greater or less than 0"

    if upgrade:
        with Status("[bold yellow]Upgrading Skeet...", console=console):
            subprocess.run("uv tool install -P skeet skeet", shell=True)
        return

    if not query:
        ctx = click.get_current_context()
        click.echo(ctx.get_help())
        ctx.exit()

    if namespace not in configurations:
        raise ValueError(f"Namespace {namespace} not found in config.yaml")

    config = configurations[namespace]

    model = model or config.get("model", DEFAULT_VALUES["model"])
    api_key = api_key or config.get("api_key", DEFAULT_VALUES["api_key"])
    interactive = not yolo or config.get("yolo", DEFAULT_VALUES["yolo"])
    attempts = attempts or config.get("attempts", DEFAULT_VALUES["attempts"])
    verify = verify or config.get("ensure", DEFAULT_VALUES["verify"])
    cleanup = cleanup or config.get("cleanup", DEFAULT_VALUES["cleanup"])
    # if verify is true or if in command mode, then we will run synchronously
    synchronous = (
        synchronous
        or verify
        or (not python)
        or config.get("synchronous", DEFAULT_VALUES["synchronous"])
    )
    python = python or config.get("python", DEFAULT_VALUES["python"])
    litellm_kwargs = config.get("litellm_kwargs", {})

    if interactive and not attempts < 0:
        if verbose:
            console.print(
                "[yellow]Interactive mode is enabled. Settings attempts below zero to allow infinite attempts.[/yellow]"
            )
        attempts = -1

    if verbose > 2:
        os.environ["LITELLM_LOG"] = "DEBUG"

    if verbose:
        pprint(
            {
                "model": model,
                "api_key": api_key[:5] + "..." + api_key[-5:] if api_key else None,
                "interactive": interactive,
                "attempts": attempts,
                "verify": verify,
                "cleanup": cleanup,
                "synchronous": synchronous,
                "python": python,
                "litellm_kwargs": litellm_kwargs,
            }
        )

    @llm(
        system=COMMAND_SYSTEM_PROMPT,
        memory=True,
        model=model,
        stream=not synchronous,
        json_schema=Result.model_json_schema() if verify else None,
        **litellm_kwargs,
    )
    def get_or_analyze_command(
        query: str,
        platform: str = platform.platform(),
        shell: str = get_shell_info(),
    ):
        """
        Create or modify an appropriate terminal command or shell script based on the query, platform, and shell.

        If the query is to be satisfied, the terminal command or shell script must return a zero exit code. For example, if the query is 'what is using port 8000', account for when the port is not being used like so: 'lsof -i :8000 || echo "port 8000 is not being used"'

        Do not include exposition or commentary.

        Query: '{query}'
        Platform: {platform}
        Shell: {shell}
        """

    verification_instructions = """
        Return the terminal command along with whether you have seen the last terminal output, the query was satisfied, and a message to the user.
        If the query was satisfied and you have seen the last terminal output, the message_to_user should be a concise summary of the terminal output.
    """

    if verify:
        get_or_analyze_command.__doc__ += os.linesep + verification_instructions
    if not synchronous:
        get_or_analyze_command.__doc__ += (
            os.linesep
            + f"Enclose the command in triple backticks with {get_shell_info()} as the shell."
        )

    json_schema = Result.model_json_schema() if verify else None

    @llm(
        system=PYTHON_SYSTEM_PROMPT,
        memory=True,
        model=model,
        stream=not synchronous,
        json_schema=json_schema,
        **litellm_kwargs,
    )
    def get_or_analyze_python_script(
        query: str,
        platform: str = platform.platform(),
    ):
        """
        Create or modify a Python script based on the query and platform. Focus on the script -- avoid unnecessary exposition or commentary.

        If last_terminal_output is provided, analyze it for errors and make necessary corrections.

        Query: '{query}'
        Platform: {platform}
        """

    verification_instructions = """
        Return the script along with whether you have seen the last terminal output, the query was satisfied, and a message to the user.
        If the query was satisfied and you have seen the last terminal output, the message_to_user should be a concise summary of the terminal output.
    """

    if verify:
        get_or_analyze_python_script.__doc__ += os.linesep + verification_instructions
    if not synchronous:
        get_or_analyze_python_script.__doc__ += (
            os.linesep
            + "Enclose the script in triple backticks with python as the language."
        )

    if api_key:
        litellm.api_key = api_key

    query_text = " ".join(query)

    last_output = None
    iteration = 0
    return_code = -1
    user_message = None

    while attempts < 0 or iteration < attempts:
        iteration += 1

        if verbose > 1:
            pprint({"iteration": iteration, "return_code": return_code})

        if return_code == 0 and not verify:
            return

        def postprocess_result(func):
            """Postprocess the result of the LLM call."""

            def wrapper(*args, **kwargs):
                result: str | dict = func(*args, **kwargs)
                if isinstance(result, dict):
                    return result
                else:
                    # some models will incorrectly set the script language to toml
                    return result.replace("```toml", "```python")

            return wrapper

        @postprocess_result
        def execute_llm(
            query_text=query_text,
            user_message=user_message,
            last_output=last_output,
            json_schema=json_schema,
        ) -> dict | str:
            import json

            method = get_or_analyze_python_script if python else get_or_analyze_command
            sudo_in_query_in_command_mode = "sudo" in query_text and not python
            query_text = (
                query_text
                if not sudo_in_query_in_command_mode
                else "YOU CANNOT USE SUDO"
            )
            response_format = (
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "Result",
                        "schema": json_schema,
                    },
                }
                if verify
                else None
            )

            if user_message:
                invocation = method.message(
                    user_message, response_format=response_format
                )
                user_message = None
            elif last_output:
                invocation = method.message(
                    f"Last Output: ```{last_output}```", response_format=response_format
                )
                last_output = None
            else:
                invocation = method(query_text)

            if synchronous:
                if isinstance(invocation, str) and verify:
                    invocation = json.loads(invocation)
                return invocation

            result = ""
            for chunk in invocation:
                if verbose or not verify:
                    console.print(chunk, end="")
                result += chunk
            print()
            return result

        if verify:
            with Status("[bold yellow]Communicating with LLM...", console=console):
                result = Result(**execute_llm())
        else:
            if synchronous:
                with Status("[bold yellow]Communicating with LLM...", console=console):
                    result_string = execute_llm()
            else:
                result_string = execute_llm()

            if python:
                try:
                    script = re.search(
                        r"```python\n(.*?)```", result_string, re.DOTALL
                    ).group(1)
                except AttributeError:
                    console.print(
                        "[yellow]Failed to extract script from output.[/yellow]"
                    )
                    console.print(
                        Panel(result_string, title="LLM Output", border_style="yellow")
                    )
                    # assume the script is the result_string
                    script = result_string

                result = Result(
                    command_or_script=script,
                    message_to_user="",
                    the_query_was_satisfied=False,
                    i_have_seen_the_last_terminal_output=False,
                )

            else:
                try:
                    terminal_command = re.search(
                        r"```(?:\w+)?\n(.*?)```", result_string, re.DOTALL
                    ).group(1)
                except AttributeError:
                    # assume the script is the result_string
                    terminal_command = result_string

                result = Result(
                    command_or_script=terminal_command,
                    message_to_user="",
                    the_query_was_satisfied=False,
                    i_have_seen_the_last_terminal_output=False,
                )

        if iteration == attempts:
            console.print("[red]Maximum iterations reached without success[/red]")
            return

        def display_result():
            console.print(
                Panel(
                    last_output,
                    title="Output",
                    subtitle=script_path if python and not cleanup else "",
                    border_style="green" if return_code == 0 else "red",
                )
            )

        if all(
            [
                result.i_have_seen_the_last_terminal_output,
                result.the_query_was_satisfied,
                last_output,
                return_code == 0,
            ]
        ):
            if verify:
                display_result()
            return

        if synchronous:
            if python:
                console.print(
                    Panel(Syntax(result.command_or_script, "python"), title="Script")
                )
            else:
                console.print(
                    Panel(
                        Syntax(result.command_or_script, get_shell_info()),
                        title="Command",
                    )
                )

        if interactive:
            user_message = Prompt.ask(
                os.linesep
                + "[magenta]What changes would you like to make? Hit [bold red]Enter[/] to run without changes.[/]",
                default="",
            )
            if user_message:
                continue

        if python:
            last_output, return_code, script_path = run_script(
                result.command_or_script,
                cleanup,
                verbose,
            )
        else:
            last_output, return_code = run_command(result.command_or_script, verbose)

        if result.message_to_user and synchronous:
            console.print(Panel(result.message_to_user, title="LLM"))

        if not verify:
            display_result()


if __name__ == "__main__":
    main()
