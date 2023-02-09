# dotfiles
![license](https://img.shields.io/github/license/cawaltrip/dotfiles)

![chezmoi](https://img.shields.io/badge/chezmoi-4051b5?style=for-the-badge&logo=data:image/svg%2bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbDpzcGFjZT0icHJlc2VydmUiIHdpZHRoPSI0Ni4wNzkiIGhlaWdodD0iMzcuNzYiIHN0eWxlPSJzaGFwZS1yZW5kZXJpbmc6Z2VvbWV0cmljUHJlY2lzaW9uO3RleHQtcmVuZGVyaW5nOmdlb21ldHJpY1ByZWNpc2lvbjtpbWFnZS1yZW5kZXJpbmc6b3B0aW1pemVRdWFsaXR5O2ZpbGwtcnVsZTpldmVub2RkO2NsaXAtcnVsZTpldmVub2RkIiB2aWV3Qm94PSIwIDAgMTIxOSA5OTkiPjxkZWZzPjxzdHlsZT4ud2hpdGV7ZmlsbDojZmZmfTwvc3R5bGU+PC9kZWZzPjxnIGlkPSJMYXllcl94MDAyMF8xIj48ZyBpZD0iXzEwMzY1NTAyMDgiPjxwYXRoIGQ9Im02MzQgMjUgMjQ0IDIwNiAyNDUgMjA1IDkxIDc3SDk0MnYyNThjOTggMjMgMTkyIDYwIDI3OSAxMDgtMTkxLTU0LTQwMS03NS02MTgtNTQtMjE4IDIxLTQyMCA4Mi01OTcgMTcyIDgxLTY4IDE3MS0xMjUgMjcwLTE2Ny0yIDEtNCAyLTYgMlY1MTNILTJsOTEtNzcgMjQ1LTIwNUw1NzggMjVsMjgtMjMgMjggMjN6bTMwOCA3NDZjLTMtMS02LTItOS0yIDMgMCA2IDEgOSAyem0tMTAtM2MtMyAwLTYtMS05LTIgMyAxIDYgMiA5IDJ6bS0xMC0yYy0zIDAtNi0xLTktMiAzIDEgNiAyIDkgMnptLTEwLTJjLTMgMC02LTEtOC0xIDIgMCA1IDEgOCAxem0tMTEtMmMtMiAwLTUtMS03LTEgMiAwIDUgMSA3IDF6bS05LTJjLTMgMC01LTEtOC0xIDMgMCA1IDEgOCAxem0tMTEtMmMtMiAwLTQgMC03LTEgMyAxIDUgMSA3IDF6bS0xMC0xYy0yLTEtNC0xLTYtMSAyIDAgNCAwIDYgMXptLTEwLTJjLTIgMC00LTEtNi0xVjQyNmgxMjFMODIyIDI5NyA2MDYgMTE1IDM4OSAyOTcgMjM2IDQyNmgxMjF2MzczYzc2LTI2IDE1NS00MyAyMzgtNTEgOTAtOSAxNzktNiAyNjYgN3ptLTU0OSA2MGMtMSAxLTMgMS00IDIgMS0xIDMtMSA0LTJ6bS05IDRjLTEgMC0zIDEtNSAxIDIgMCA0LTEgNS0xem0tOSAzLTYgMyA2LTN6bS05IDRjLTIgMS00IDItNiAyIDIgMCA0LTEgNi0yeiIgY2xhc3M9IndoaXRlIi8+PHBhdGggZD0iTTUzMiA0NDVjMC00MCAzMy03MyA3NC03MyA0MCAwIDczIDMzIDczIDczIDAgMjgtMTQgNTItMzYgNjRsNyAxMyA0NSA3N0g1MTdsNDUtNzcgNy0xM2MtMjItMTItMzctMzYtMzctNjR6IiBjbGFzcz0id2hpdGUiLz48L2c+PC9nPjwvc3ZnPg==&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-000000?style=for-the-badge&logo=Apple&logoColor=FFFFFF)
![Linux](https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black)
![Windows](https://img.shields.io/badge/Windows-00A4EF?style=for-the-badge&logo=windows&logoColor=white)


This is a collection of my dotfiles, managed with [chezmoi](https://chezmoi.io).

## Installation
1. [Install chezmoi](https://www.chezmoi.io/install/).
1. Initialize this repository.
    ```bash
    chezmoi init cawaltrip
    ```
1. Answer the questions asked during the initialization.

### Post-installation steps
After all of the applications are installed, a few have manual configuration steps.

#### Firefox
The initialization will install Firefox and create a profile including custom user chrome, and will configure Firefox to use it.  Extensions, however, aren't installed.  Open Firefox, and login to Firefox Sync to sync extensions and their settings.  The only extension I have with a lot of customization is Tree Style Tab (which is what `userChrome.css` helps style).

## License
This repository is licensed under the [MIT No Attribution](https://spdx.org/licenses/MIT-0.html) (SPDX: `MIT-0`) license.  See the [license](LICENSE) file for the full text.