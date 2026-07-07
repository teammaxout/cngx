"""Capture command for Cogscope CLI."""

import json
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer()
console = Console()


@app.command("run")
def run_capture(
    prompt: str = typer.Argument(..., help="The prompt to send to the model"),
    task_id: str = typer.Option("default", "--task", "-t", help="Task identifier"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="Model to use"),
    adapter: str = typer.Option(
        "openai", "--adapter", "-a", help="Adapter (openai, gemini, claude, mock)"
    ),
    system: Optional[str] = typer.Option(None, "--system", "-s", help="System message"),
    temperature: float = typer.Option(1.0, "--temperature", help="Temperature"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save to database"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Capture a reasoning trace from an LLM call.

    Example:
        cogscope capture run "Solve 2x + 5 = 13" --task math --model gpt-4o
    """
    from cogscope.capture.tracer import CogscopeTracer

    tracer = CogscopeTracer(adapter=adapter, model=model, temperature=temperature)

    console.print(f"[dim]Capturing trace for task '{task_id}'...[/]")

    try:
        trace = tracer.capture(
            prompt=prompt,
            task_id=task_id,
            system_message=system,
            save=save,
        )

        if json_output:
            print(json.dumps(trace.model_dump(mode="json"), indent=2, default=str))
        else:
            # Get fingerprint
            fp = tracer.get_fingerprint(trace.id)

            console.print(
                Panel(
                    f"[bold]Trace ID:[/] {trace.id}\n"
                    f"[bold]Task:[/] {task_id}\n"
                    f"[bold]Model:[/] {trace.model}\n"
                    f"[bold]Latency:[/] {trace.latency_ms:.0f}ms\n"
                    f"[bold]Tokens:[/] {trace.token_usage.total_tokens}\n\n"
                    f"[bold]Output:[/]\n{trace.output[:500]}{'...' if len(trace.output) > 500 else ''}\n\n"
                    + (
                        f"[bold]Fingerprint:[/]\n"
                        f"  Depth: {fp.depth}\n"
                        f"  Steps: {fp.total_steps}\n"
                        f"  Tools: {fp.tool_call_count}\n"
                        f"  Corrections: {fp.correction_count}\n"
                        f"  Verification: {fp.verification_steps}\n"
                        f"  Signature: {fp.signature_hash}"
                        if fp
                        else ""
                    ),
                    title="[green]Trace Captured[/]",
                )
            )

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command("batch")
def batch_capture(
    input_file: typer.FileText = typer.Argument(..., help="JSON file with prompts"),
    task_id: str = typer.Option("batch", "--task", "-t", help="Base task identifier"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="Model to use"),
    adapter: str = typer.Option("openai", "--adapter", "-a", help="Adapter"),
) -> None:
    """Batch capture traces from a file.

    Input file should be JSON with format:
    [
        {"prompt": "...", "task_id": "...", "system": "..."},
        ...
    ]
    """
    import json

    from cogscope.capture.tracer import CogscopeTracer

    tracer = CogscopeTracer(adapter=adapter, model=model)

    data = json.load(input_file)
    results = []

    with console.status("[bold]Capturing traces...") as status:
        for i, item in enumerate(data):
            prompt = item.get("prompt", "")
            item_task = item.get("task_id", f"{task_id}_{i}")
            system = item.get("system")

            status.update(f"[bold]Capturing {i+1}/{len(data)}...")

            try:
                trace = tracer.capture(
                    prompt=prompt,
                    task_id=item_task,
                    system_message=system,
                )
                results.append({"trace_id": trace.id, "status": "success"})
                console.print(f"[green]✓[/] {item_task}: {trace.id}")
            except Exception as e:
                results.append({"task_id": item_task, "status": "error", "error": str(e)})
                console.print(f"[red]✗[/] {item_task}: {e}")

    success = sum(1 for r in results if r["status"] == "success")
    console.print(f"\n[bold]Captured {success}/{len(data)} traces[/]")


@app.command("mock")
def mock_capture(
    task_id: str = typer.Argument("demo", help="Task identifier"),
    preset: str = typer.Option("default", "--preset", "-p", help="Behavioral preset"),
    count: int = typer.Option(1, "--count", "-n", help="Number of traces to generate"),
    prompt: str = typer.Option("Explain quantum computing", "--prompt", help="Prompt"),
) -> None:
    """Generate mock traces for testing.

    Presets: default, verbose, terse, tool_heavy, uncertain, confident
    """
    from cogscope.capture.tracer import CogscopeTracer

    tracer = CogscopeTracer(adapter="mock", model="mock-model", preset=preset)

    console.print(f"[dim]Generating {count} mock trace(s) with preset '{preset}'...[/]")

    for i in range(count):
        trace = tracer.capture(
            prompt=f"{prompt} (variant {i+1})" if count > 1 else prompt,
            task_id=task_id,
        )
        fp = tracer.get_fingerprint(trace.id)

        console.print(
            f"[green]✓[/] {trace.id} - depth:{fp.depth} tools:{fp.tool_call_count} sig:{fp.signature_hash}"
        )

    console.print(f"\n[bold]Generated {count} trace(s)[/]")


@app.callback()
def callback() -> None:
    """Capture reasoning traces from LLM calls."""
    pass
