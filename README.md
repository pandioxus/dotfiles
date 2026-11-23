# Dotfiles

My dotfiles for a normal linux distribution :P
One of the most convinent features of NixOS is the ability to manage user program dotfiles using Home Manager. The [[ricer.py]] file is my take on finding a good middle ground for a reliable dotfiles manager. The ricer script itself is strictly single file for sake of convenience.

> NOTE: The ricer script was generated 100% Claude AI, because I'm too lazy to deal with python scripts. And the section of README that talks about the script

# Ricer.py
## Features

- **Three deployment modes per file or directory:**
  - **Staged symlinks (default):** Copied into `.ricer/build/` and symlinked to the destination—isolating live configs from accidental edits in your repo.
  - **Direct copies (`!!`):** Copied straight to the destination and tracked via SHA-256 content hashes.
  - **Direct symlinks (`!!!`):** Symlinked directly to the source file or directory in your repo for instant live editing.
- **Convention-based destination mapping:**
  - `home/` deploys to `$HOME`
  - `<package>/` deploys to `$XDG_CONFIG_HOME/<package>` (defaults to `~/.config/<package>`)
  - Custom destinations via a `.ricer_out` marker file
- **Safe conflict handling & drift detection:** Detects when a target has been modified outside `ricer` and prompts you to `delete`, `backup`, or `skip`—and refuses to overwrite or delete locally edited files during `remove`.
- **Dry runs & action logging:** Preview every operation with `--dry-run` and inspect past changes in `.ricer/actions.json`.

## Requirements

- Python 3.8+ (uses only the Python standard library)

## Usage
```bash
# Apply dotfiles (default command)
python3 ricer.py
python3 ricer.py apply

# Preview planned operations without making changes
python3 ricer.py --dry-run
python3 ricer.py -n

# Resolve all conflicts automatically without prompting
python3 ricer.py apply --policy backup   # choices: delete, backup, skip

# Remove all targets previously deployed by ricer (preserves locally edited targets)
python3 ricer.py remove
python3 ricer.py remove --dry-run
```
