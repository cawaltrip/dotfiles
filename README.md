# dotfiles
![license](https://img.shields.io/github/license/cawaltrip/dotfiles)

![chezmoi](https://img.shields.io/badge/chezmoi-4051b5?style=for-the-badge&logo=data:image/svg%2bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbDpzcGFjZT0icHJlc2VydmUiIHdpZHRoPSI0Ni4wNzkiIGhlaWdodD0iMzcuNzYiIHN0eWxlPSJzaGFwZS1yZW5kZXJpbmc6Z2VvbWV0cmljUHJlY2lzaW9uO3RleHQtcmVuZGVyaW5nOmdlb21ldHJpY1ByZWNpc2lvbjtpbWFnZS1yZW5kZXJpbmc6b3B0aW1pemVRdWFsaXR5O2ZpbGwtcnVsZTpldmVub2RkO2NsaXAtcnVsZTpldmVub2RkIiB2aWV3Qm94PSIwIDAgMTIxOSA5OTkiPjxkZWZzPjxzdHlsZT4ud2hpdGV7ZmlsbDojZmZmfTwvc3R5bGU+PC9kZWZzPjxnIGlkPSJMYXllcl94MDAyMF8xIj48ZyBpZD0iXzEwMzY1NTAyMDgiPjxwYXRoIGQ9Im02MzQgMjUgMjQ0IDIwNiAyNDUgMjA1IDkxIDc3SDk0MnYyNThjOTggMjMgMTkyIDYwIDI3OSAxMDgtMTkxLTU0LTQwMS03NS02MTgtNTQtMjE4IDIxLTQyMCA4Mi01OTcgMTcyIDgxLTY4IDE3MS0xMjUgMjcwLTE2Ny0yIDEtNCAyLTYgMlY1MTNILTJsOTEtNzcgMjQ1LTIwNUw1NzggMjVsMjgtMjMgMjggMjN6bTMwOCA3NDZjLTMtMS02LTItOS0yIDMgMCA2IDEgOSAyem0tMTAtM2MtMyAwLTYtMS05LTIgMyAxIDYgMiA5IDJ6bS0xMC0yYy0zIDAtNi0xLTktMiAzIDEgNiAyIDkgMnptLTEwLTJjLTMgMC02LTEtOC0xIDIgMCA1IDEgOCAxem0tMTEtMmMtMiAwLTUtMS03LTEgMiAwIDUgMSA3IDF6bS05LTJjLTMgMC01LTEtOC0xIDMgMCA1IDEgOCAxem0tMTEtMmMtMiAwLTQgMC03LTEgMyAxIDUgMSA3IDF6bS0xMC0xYy0yLTEtNC0xLTYtMSAyIDAgNCAwIDYgMXptLTEwLTJjLTIgMC00LTEtNi0xVjQyNmgxMjFMODIyIDI5NyA2MDYgMTE1IDM4OSAyOTcgMjM2IDQyNmgxMjF2MzczYzc2LTI2IDE1NS00MyAyMzgtNTEgOTAtOSAxNzktNiAyNjYgN3ptLTU0OSA2MGMtMSAxLTMgMS00IDIgMS0xIDMtMSA0LTJ6bS05IDRjLTEgMC0zIDEtNSAxIDIgMCA0LTEgNS0xem0tOSAzLTYgMyA2LTN6bS05IDRjLTIgMS00IDItNiAyIDIgMCA0LTEgNi0yeiIgY2xhc3M9IndoaXRlIi8+PHBhdGggZD0iTTUzMiA0NDVjMC00MCAzMy03MyA3NC03MyA0MCAwIDczIDMzIDczIDczIDAgMjgtMTQgNTItMzYgNjRsNyAxMyA0NSA3N0g1MTdsNDUtNzcgNy0xM2MtMjItMTItMzctMzYtMzctNjR6IiBjbGFzcz0id2hpdGUiLz48L2c+PC9nPjwvc3ZnPg==&logoColor=white)
![Bitwarden](https://img.shields.io/static/v1?style=for-the-badge&message=Bitwarden&color=175DDC&logo=Bitwarden&logoColor=FFFFFF&label=)
![AWSsecretsmanager](https://img.shields.io/badge/AWS%20Secrets%20Manager-ff5252?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbDpzcGFjZT0icHJlc2VydmUiIHN0eWxlPSJlbmFibGUtYmFja2dyb3VuZDpuZXcgMCAwIDU2IDU2IiB2aWV3Qm94PSIwIDAgNTYgNTYiPjxwYXRoIGQ9Ik0yNi44IDMxLjRjMCAuNy42IDEuMiAxLjIgMS4yLjcgMCAxLjItLjYgMS4yLTEuMiAwLS43LS42LTEuMi0xLjItMS4yLS43LS4xLTEuMi41LTEuMiAxLjJ6bS0yIDBjMC0xLjggMS41LTMuMiAzLjItMy4yczMuMiAxLjUgMy4yIDMuMmMwIDEuNC0uOSAyLjYtMi4yIDMuMVYzN2gtMnYtMi42Yy0xLjMtLjQtMi4yLTEuNi0yLjItM3pNMzcgMjZIMTl2MTNoMTh2LTNoLTN2LTJoM3YtM2gtM3YtMmgzdi0zem0tMTUtMmgxMnYtNWMwLTIuNi0yLjktNS02LTUtMS41IDAtMy4xLjYtNC4yIDEuNlMyMiAxNy44IDIyIDE5djV6bTE0LTV2NWgyYy42IDAgMSAuNCAxIDF2MTVjMCAuNi0uNCAxLTEgMUgxOGMtLjYgMC0xLS40LTEtMVYyNWMwLS42LjQtMSAxLTFoMnYtNWMwLTEuOC45LTMuNiAyLjUtNC45QzI0IDEyLjggMjYgMTIgMjggMTJjNC4zIDAgOCAzLjMgOCA3ek03LjIgNDNsMS42LTEuMkM2LjEgMzguMSA0LjYgMzMuNyA0LjQgMjlIN3YtMkg0LjRjLjItNC42IDEuNy05IDQuNC0xMi44TDcuMiAxM2MtMyA0LjEtNC42IDguOS00LjggMTRIMHYyaDIuNGMuMiA1LjEgMS44IDkuOSA0LjggMTR6bTM0LjYgNC4yYy0zLjggMi43LTguMiA0LjItMTIuOCA0LjRWNDloLTJ2Mi42Yy00LjYtLjItOS4xLTEuNy0xMi44LTQuNEwxMyA0OC44YzQuMSAzIDguOSA0LjYgMTQgNC44VjU2aDJ2LTIuNGM1LjEtLjIgOS45LTEuOCAxNC00LjhsLTEuMi0xLjZ6TTE0LjIgOC45QzE4IDYuMiAyMi40IDQuNyAyNyA0LjVWN2gyVjQuNGM0LjYuMiA5LjEgMS43IDEyLjggNC40TDQzIDcuMmMtNC4xLTMtOC45LTQuNi0xNC00LjhWMGgtMnYyLjRjLTUuMS4yLTkuOSAxLjgtMTQgNC44bDEuMiAxLjd6TTUzLjYgMjdjLS4yLTUuMS0xLjgtOS45LTQuOC0xNGwtMS42IDEuMmMyLjcgMy44IDQuMiA4LjIgNC40IDEyLjhINDl2MmgyLjZjLS4yIDQuNy0xLjcgOS4xLTQuNCAxMi45bDEuNiAxLjJjMy00LjEgNC42LTkgNC44LTE0SDU2di0yaC0yLjR6bS05LjItMTMuOSA3LjgtNy44LTEuNC0xLjQtNy44IDcuNyAxLjQgMS41ek0xMS42IDQzbC03LjggNy44IDEuNCAxLjQgNy44LTcuOC0xLjQtMS40em01LjEtMjcuN0wxLjguNC40IDEuOGwxNC44IDE0LjggMS41LTEuM3ptMjUuNSAyNS41IDEzLjQgMTMuNC0xLjQgMS40LTEzLjQtMTMuNCAxLjQtMS40eiIgc3R5bGU9ImZpbGwtcnVsZTpldmVub2RkO2NsaXAtcnVsZTpldmVub2RkO2ZpbGw6I2ZmZiIvPjwvc3ZnPg==&logoColor=white)



![macOS](https://img.shields.io/badge/macOS-000000?style=for-the-badge&logo=Apple&logoColor=FFFFFF)
![Linux](https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black)
![Windows](https://img.shields.io/badge/Windows-00A4EF?style=for-the-badge&logo=windows&logoColor=white)


This is a collection of my dotfiles, managed with [chezmoi](https://chezmoi.io).  Secrets are managed using the [Bitwarden CLI](https://github.com/bitwarden/clients), and [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/).

## Installation
1. [Install chezmoi](https://www.chezmoi.io/install/).
1. [Install Bitwarden CLI](https://bitwarden.com/help/cli/)
1. Configure Bitwarden.
    > **Warning**
    > Make sure that the files have the below file permissions otherwise someone else may be able to read the contents!
    ```console
    $ bw_conf=${XDG_CONFIG_HOME}/bitwarden
    $ install -d ${bw_conf}
    $ install -m 0600 /dev/null ${bw_conf}/bwpass
    $ install -m 0600 /dev/null ${bw_conf}/bwtoken
    ```
    1. The contents of `bwtoken` should be a sourceable script that export the variables `BW_CLIENTID`, and `BW_CLIENTSECRET`.  See [the personal API key help page](https://bitwarden.com/help/personal-api-key/) for steps to obtain those values.
    1. The contents of `bwpass` should be your Bitwarden password.  See [the unlock options section of the CLI help page](https://bitwarden.com/help/cli/#unlock-options) for details.
1. Login to Bitwarden.
    ```console
    $ bw login --apikey
    $ export BW_SESSION=$(bw unlock --passwordfile ${XDG_CONFIG_HOME}/bitwarden/bwpass --raw)
    ```
1. Initialize this repository.
    ```console
    $ chezmoi init cawaltrip
    ```
1. Answer the questions asked during the initialization.

### Post-installation steps
After all of the applications are installed, a few have manual configuration steps.

#### Firefox
The initialization will install Firefox and create a profile including custom user chrome, and will configure Firefox to use it.  Extensions, however, aren't installed.  Open Firefox, and login to Firefox Sync to sync extensions and their settings.  The only extension I have with a lot of customization is Tree Style Tab (which is what `userChrome.css` helps style).

## TODO
Things I'm still working on:
* Incorporate the password manager + pre-read-source-state hook better.
    * PowerShell doesn't like to run the script I've created.
    * Need to flesh out the unixlike part.
* Move shared configs to `.chezmoitemplates`.
* Install my custom version of FiraCode on Windows automatically.

## License
This repository is licensed under the [MIT No Attribution](https://spdx.org/licenses/MIT-0.html) (SPDX: `MIT-0`) license.  See the [license](LICENSE) file for the full text.