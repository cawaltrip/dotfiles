#!/usr/bin/env sh
echo --% >/dev/null;: ' | out-null
<#'
 # Run this shell script.
if command -v brew >/dev/null 2>&1; then
    brew install bitwarden-cli
elif command -v snap >/dev/null 2>&1; then
    sudo snap install bw
elif command -v apt >/dev/null 2>&1; then
    echo "install manually."
    exit 1
elif command -v pacman >/dev/null 2>&1; then
    pacman -S extra/bitwarden-cli
elif command -v dnf >/dev/null 2>&1; then
    echo "install manually."
    exit 1
fi

# Add configuration here.

exit #>

# Use winget to install if possible.
#
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    exit
}

winget install Bitwarden.CLI
