import typer
# from typing_extensions import Annotated # For older Python versions, for Python 3.9+ you can use typing.Annotated
from typing import Annotated

app = typer.Typer()

@app.command()
def greet(
    name: Annotated[str, typer.Argument(help="The name of the person to greet.")],
    greeting: Annotated[str, typer.Option(help="The greeting phrase.")] = "Hello",
    times: Annotated[int, typer.Option(help="Number of times to greet.")] = 1,
    verbose: Annotated[bool, typer.Option(help="Enable verbose output.")] = False,
):
    """
    A simple tool to greet someone, built with Typer.
    """
    if verbose:
        typer.echo(f"Verbose mode enabled.") # typer.echo is like print but with more features
        typer.echo(f"Received arguments: name='{name}', greeting='{greeting}', times={times}")

    for _ in range(times):
        typer.secho(f"{greeting}, {name}!", fg=typer.colors.GREEN) # secho allows styling

    if verbose:
        typer.echo("Greeting complete.")

@app.command()
def goodbye(
    name: Annotated[str, typer.Argument(help="The name of the person.")],
    formal: Annotated[bool, typer.Option(help="Use a formal goodbye.")] = False
):
    """
    Say goodbye to someone.
    """
    if formal:
        typer.echo(f"Farewell, {name}.")
    else:
        typer.echo(f"Bye, {name}!")


if __name__ == "__main__":
    app()