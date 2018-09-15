#!/usr/bin/env bash

# Create a master gitignore file by using gitignore.io
# Filename is from root of dotfiles directory (where shell script
# is run from).
filename="./configs/git/gitignore"
gitignore_io="https://www.gitignore.io"
api="${gitignore_io}/api"

# Is website available?
status=$(curl -s -o /dev/null -I -w "%{http_code}" "${gitignore_io}")
if [[ "${status}" -ge 200 ]] && [[ "${status}" -lt 400 ]]; then
	# gitignore.io API wants csv of the ignore files to grab
	ignore_list="linux,windows,macos"
	ignore_list+=",vim,emacs,sublimetext,jetbrains+all,visualstudio,visualstudiocode,textmate"
	ignore_list+=",ansible,vagrant,autotools,mercurial,sketchup"
	ignore_list+=",python,pydev,jupyternotebook,virtualenv"

	curl -s -o "${filename}" "${api}/${ignore_list}"
fi
