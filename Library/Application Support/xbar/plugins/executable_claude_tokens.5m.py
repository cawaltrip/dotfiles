#!/usr/bin/env python3

# <xbar.title>Claude Token Usage</xbar.title>
# <xbar.version>v1.0</xbar.version>
# <xbar.author>Preslav Rachev</xbar.author>
# <xbar.desc>Shows today's Claude Code token usage in the Mac toolbar</xbar.desc>

import glob
import json
import os
import subprocess
from datetime import datetime
from typing import Any


def format_number(num):
    """Formats a number into a human-readable string with K/M suffixes."""
    if num >= 1000000:
        return f"{num / 1000000:.1f}M"
    if num >= 1000:
        return f"{num / 1000:.1f}K"
    return str(num)


def get_ccusage_data() -> dict[str, Any]:
    """Fetches Claude Code usage statistics via the pinned `npx ccusage@20.0.14 -j` command.

    This version emits a per-model `modelBreakdowns` array in each daily entry,
    which powers the "By Model" submenu. Older versions (e.g. v19.0.3) omit it,
    and the breakdown section degrades gracefully when it is absent.
    """
    try:
        # Set up environment with common paths for xbar
        env = os.environ.copy()

        # Add common Node.js paths to ensure npx is found
        common_paths = [
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            "/opt/homebrew/bin",  # Homebrew on Apple Silicon
            os.path.expanduser("~/.nvm/versions/node/*/bin"),  # NVM paths
            os.path.expanduser("~/node_modules/.bin"),  # Local node modules
        ]

        # Expand glob patterns and filter existing paths
        expanded_paths = []
        for path in common_paths:
            if "*" in path:
                expanded_paths.extend(glob.glob(path))
            elif os.path.exists(path):
                expanded_paths.append(path)

        # Add to PATH if not already present
        current_path = env.get("PATH", "")
        for path in expanded_paths:
            if path not in current_path:
                current_path = f"{path}:{current_path}"
        env["PATH"] = current_path

        # Try running npx from PATH
        result = subprocess.run(
            ["npx", "ccusage@20.0.14", "-j"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=env,
        )

        if result.returncode == 0:
            return json.loads(result.stdout)

        return {
            "error": f"Command failed with code {result.returncode}",
            "stderr": result.stderr,
            "stdout": result.stdout,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out after 30 seconds"}
    except json.JSONDecodeError as e:
        return {"error": f"JSON decode error: {e}", "stdout": result.stdout}
    except FileNotFoundError:
        return {"error": "npx command not found - Node.js may not be installed"}


def format_model_name(model_name: str) -> str:
    """Shortens a ccusage model id for display.

    e.g. 'claude-haiku-4-5-20251001' -> 'haiku-4-5', 'claude-opus-4-8' -> 'opus-4-8'.
    """
    name = model_name.removeprefix("claude-")
    parts = name.split("-")
    # Drop a trailing 8-digit date stamp segment if present (e.g. '-20251001').
    if parts and len(parts[-1]) == 8 and parts[-1].isdigit():
        parts = parts[:-1]
    return "-".join(parts)


def print_model_breakdown(today_usage: dict[str, Any]) -> None:
    """Prints today's per-model cost/token breakdown as an xbar submenu section.

    No-ops when the daily entry has no `modelBreakdowns` array (older ccusage).
    """
    breakdowns = today_usage.get("modelBreakdowns") or []
    if not breakdowns:
        return

    day_cost = today_usage.get("totalCost", 0) or 0

    print("---")
    print("By Model (Today)")
    for model in sorted(breakdowns, key=lambda m: m.get("cost", 0), reverse=True):
        name = format_model_name(model.get("modelName", "unknown"))
        cost = model.get("cost", 0)
        share = f"{cost / day_cost * 100:.0f}%" if day_cost else "—"
        model_tokens = (
            model.get("inputTokens", 0)
            + model.get("outputTokens", 0)
            + model.get("cacheCreationTokens", 0)
            + model.get("cacheReadTokens", 0)
        )
        print(f"{name}  ${cost:.2f}  ({share})")
        print(f"--Tokens: {format_number(model_tokens)}")
        print(f"--Input: {format_number(model.get('inputTokens', 0))}")
        print(f"--Output: {format_number(model.get('outputTokens', 0))}")
        print(f"--Cache Creation: {format_number(model.get('cacheCreationTokens', 0))}")
        print(f"--Cache Read: {format_number(model.get('cacheReadTokens', 0))}")


def main():
    """Main function to fetch and display Claude Code usage statistics."""
    # Get today's date in YYYY-MM-DD format
    today = datetime.now().strftime("%Y-%m-%d")

    # Get usage data
    data = get_ccusage_data()

    if not data or (isinstance(data, dict) and "error" in data):
        print("⚠️ Error")
        print("---")
        if isinstance(data, dict) and "error" in data:
            print(f"Error: {data['error']}")
            if "stderr" in data:
                print(f"Stderr: {data['stderr']}")
            if "stdout" in data:
                print(f"Stdout: {data['stdout']}")
        else:
            print("Failed to fetch usage data")
        return

    # Find today's usage. ccusage keys the daily date as "period"; older
    # versions used "date", so fall back to it for resilience.
    today_usage = None
    for day in data.get("daily", []):
        if (day.get("period") or day.get("date")) == today:
            today_usage = day
            break

    if not today_usage:
        print("📊 0 tokens")
        print("---")
        print("No usage today")
        return

    # Display today's token count in toolbar
    total_tokens = today_usage.get("totalTokens", 0)
    total_cost = today_usage.get("totalCost", 0)

    print(f"📊 ${total_cost:.2f} · {format_number(total_tokens)}")
    print("---")
    print(f"Today's Usage ({today})")
    print(f"Total Tokens: {format_number(total_tokens)}")
    print(f"Input: {format_number(today_usage.get('inputTokens', 0))}")
    print(f"Output: {format_number(today_usage.get('outputTokens', 0))}")
    print(f"Cache Creation: {format_number(today_usage.get('cacheCreationTokens', 0))}")
    print(f"Cache Read: {format_number(today_usage.get('cacheReadTokens', 0))}")
    print(f"Cost: ${total_cost:.2f}")

    # Per-model breakdown (only present in newer ccusage output)
    print_model_breakdown(today_usage)

    print("---")

    # Show total usage
    totals = data.get("totals", {})

    print("Total Usage (All Time)")
    print(f"Total Tokens: {format_number(totals.get('totalTokens', 0))}")
    print(f"Total Cost: ${totals.get('totalCost', 0):.2f}")


if __name__ == "__main__":
    main()
