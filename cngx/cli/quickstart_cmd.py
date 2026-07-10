"""cngx quickstart: a real, zero-key demo of catching an agent's false claim.

This runs actual tests in a throwaway project (via the stdlib unittest runner,
so it needs no API keys and no extra packages) and shows cngx blocking a merge
when the agent claims the tests pass but they do not.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

console = Console(stderr=True)

_MODULE_BUGGY = """\
def paginate(items, page, size):
    # 0-based offset, but the API contract says pages are 1-based
    return items[page * size:(page + 1) * size]
"""

_MODULE_FIXED = """\
def paginate(items, page, size):
    return items[(page - 1) * size:page * size]
"""

_TESTS = """\
import unittest
from cart import paginate


class PaginationTests(unittest.TestCase):
    def test_first_page(self):
        self.assertEqual(paginate([1, 2, 3, 4, 5, 6], 1, 2), [1, 2])

    def test_second_page(self):
        self.assertEqual(paginate([1, 2, 3, 4, 5, 6], 2, 2), [3, 4])

    def test_page_size(self):
        self.assertEqual(len(paginate(list(range(100)), 1, 10)), 10)


if __name__ == "__main__":
    unittest.main()
"""

_AGENT_CLAIM = (
    "Fixed the pagination off-by-one. Ran the test suite and all tests pass, "
    "3 passed, no failures. The change is ready to merge."
)


def _run(project: Path):
    from cngx.verify.claims import extract_claim
    from cngx.verify.parsers import parse_output
    from cngx.verify.runner import run_command
    from cngx.verify.verdict import decide

    command = [sys.executable, "-m", "unittest", "-v"]
    result_run = run_command(command, timeout=120.0, cwd=str(project))
    parsed = parse_output(result_run.combined, exit_code=result_run.exit_code)
    claim = extract_claim(_AGENT_CLAIM)
    verdict = decide(parsed, claim, command_label="python -m unittest")
    return verdict, result_run


def run_quickstart() -> None:
    start = time.monotonic()
    console.print()
    console.print(
        Panel(
            "[bold white]cngx quickstart[/]\n\n"
            "An AI agent says it fixed a bug and [italic]all tests pass[/]. cngx runs\n"
            "the tests it claimed to run and checks whether that is actually true.\n"
            "No API keys, no setup.",
            border_style="cyan",
            padding=(1, 2),
        )
    )

    with tempfile.TemporaryDirectory(prefix="cngx-quickstart-") as tmp:
        project = Path(tmp)
        (project / "cart.py").write_text(_MODULE_BUGGY, encoding="utf-8")
        (project / "test_cart.py").write_text(_TESTS, encoding="utf-8")

        console.print()
        console.print(Rule("[bold]The agent says[/]", style="yellow"))
        console.print(f"  [italic]{_AGENT_CLAIM}[/]")
        console.print()

        console.print(Rule("[bold]cngx verify -- python -m unittest[/]", style="cyan"))
        verdict, run_result = _run(project)
        _print_verdict(verdict, run_result.combined)

        console.print()
        console.print(Rule("[bold]After a real fix[/]", style="green"))
        (project / "cart.py").write_text(_MODULE_FIXED, encoding="utf-8")
        verdict2, _ = _run(project)
        _print_verdict(verdict2, "")

    elapsed = time.monotonic() - start
    console.print()
    console.print(
        Panel(
            "[bold]That is the whole idea.[/]\n\n"
            "The agent's message alone looked merge-ready. cngx ignored the prose\n"
            "and ran the real checks, so a false claim cannot pass.\n\n"
            "Use it on your own repo:\n"
            "  [cyan]cngx verify --output-file agent.md -- pytest[/]\n"
            "  [cyan]cngx verify -- npm test[/]      (any command works)\n"
            "  [cyan]cngx verify -e ci_test.log[/]   (gate an existing CI log)\n\n"
            f"[dim]completed in {elapsed:.1f}s[/]",
            title="[bold]next[/]",
            border_style="green",
        )
    )


def _print_verdict(verdict, real_output: str) -> None:
    from cngx.verify.verdict import BLOCKED, VERIFIED

    if verdict.status == VERIFIED:
        tag, border = "[bold green]VERIFIED[/]", "green"
    elif verdict.status == BLOCKED:
        tag, border = "[bold red]BLOCKED[/]", "red"
    else:
        tag, border = "[bold yellow]ERROR[/]", "yellow"

    lines = [f"{tag}  {verdict.headline}"]
    for reason in verdict.reasons:
        lines.append(f"  {reason}")
    console.print(Panel("\n".join(lines), border_style=border, padding=(0, 2)))
