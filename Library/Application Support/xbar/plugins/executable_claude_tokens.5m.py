#!/usr/bin/env python3

# <xbar.title>Claude Token Usage</xbar.title>
# <xbar.version>v1.0</xbar.version>
# <xbar.author>Preslav Rachev</xbar.author>
# <xbar.desc>Shows today's Claude Code token usage in the Mac toolbar</xbar.desc>

import json
import subprocess
import os
import glob
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
    """Fetches Claude Code usage statistics using the `npx ccusage@latest -j` command."""
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
            ["npx", "ccusage@latest", "-j"],
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

    # Find today's usage
    today_usage = None
    for day in data.get("daily", []):
        if day.get("date") == today:
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

    print(f"📊 {format_number(total_tokens)}")
    print("---")
    print(f"Today's Usage ({today})")
    print(f"Total Tokens: {format_number(total_tokens)}")
    print(f"Input: {format_number(today_usage.get('inputTokens', 0))}")
    print(f"Output: {format_number(today_usage.get('outputTokens', 0))}")
    print(f"Cache Creation: {format_number(today_usage.get('cacheCreationTokens', 0))}")
    print(f"Cache Read: {format_number(today_usage.get('cacheReadTokens', 0))}")
    print(f"Cost: ${total_cost:.2f}")
    print("---")

    # Show total usage
    totals = data.get("totals", {})

    print("Total Usage (All Time)")
    print(f"Total Tokens: {format_number(totals.get('totalTokens', 0))}")
    print(f"Total Cost: ${totals.get('totalCost', 0):.2f}")


if __name__ == "__main__":
    main()
