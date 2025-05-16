# Emacs bindings (makes Ctrl-D work as expected):
Set-PSReadlineOption -EditMode Emacs

# Aliases
. "$PSScriptRoot\aliases.ps1"

# Start starship for the prompt
Invoke-Expression (&starship init powershell)