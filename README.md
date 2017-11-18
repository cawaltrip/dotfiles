dotfiles
========

[![License: CC0 1.0 Universal](https://licensebuttons.net/l/zero/1.0/88x15.png)](https://creativecommons.org/publicdomain/zero/1.0/)

This is a collection of my personal configuration files.  While it currently is limited to only my Linux workstation configuration, it will eventually be expanded to also store my Windows environment configurations as well.

These dotfiles use [Dotbot][dotbot] for installation.

Requirements
============

If you don't care about a cluttered configuration area and want to have configuration files for all sorts of software that you may or may not use, then the only requirements are the following:

 * [Dotbot][dotbot] >= 1.0.0
 * git >= 1.9.3
 * python >= 2.7/3.2 (for [Dotbot][dotbot])

Installation
============

Installation is as simple as cloning and running the installation script:

```
git clone --recursive https://github.com/cawaltrip/dotfiles ~/.dotfiles
cd ~/.dotfiles
./install-profile workstation
```

Configuration
=============

Configuration is done by placing:
 1.  Placing the configuration files inside `./configs/` in a meaningful way (e.g., `bash` configuration files inside `./configs/shells/bash`);
 1.  Creating/modifiying the YaML file in `./meta/configs/` in order to define where the configuration file should be placed (e.g., adding the `bash` configuration file metadata in `./meta/configs/bash.yaml`); and 
 1.  Adding the name of the YaML file (without file extension) to a profile in `./meta/profiles/` - one YaML filename per line (e.g., adding "bash" to `./meta/profiles/workstation` for `bash.yaml`).

If you would like to refresh all of the dotfiles afterwards, just run the installation script for the profile that you'd like.

There is also a standalone installer (`./install-standalone`) that only runs the instructions found in `./meta/base.yaml` if desired.

License
=======

This work is licensed under the Creative Commons CC0 1.0 Universal license.  This means that no copyright is reserved and I am relinquishing all copyright and other similar rights that I hold for this work and am dedicating those rights to the public domain.  See the [license][license] for additional information.

This license only holds for work that is my own and is in this repository.  Any work that is not my own or is a part of a git submodule falls under the license for that respective work.

Credits
=======

 * [anishathalye][anishathalye] for creating and maintaining [Dotbot][dotbot].
 * [vsund][vsund] ([vsund-dotfiles][repo]), [vbrandi][vbrandi] ([vbrandi-dotfiles][repo]), and [magicmonty][magicmonty] ([magicmonty-dotfiles][repo]) for the directory structure inspiration.


[dotbot]: https://github.com/anishathalye/dotbot
[license]: LICENSE.md
[anishathalye]: https://github.com/anishathalye
[vbrandi]: https://github.com/vbrandi
[vbrandi-dotfiles]: https://github.com/vbrandi/dotfiles
[vsund]: https://github.com/vsund/
[vsund-dotfiles]: https://github.com/vsund/dotfiles
[magicmonty]: https://github.com/magicmonty
[magicmonty-dotfiles]: https://github.com/magicmonty/dotfiles_dotbot
