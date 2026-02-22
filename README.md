# easy-worktree-tui (wtt)

A rich TUI (Terminal User Interface) companion for [easy-worktree](https://github.com/igtm/easy-worktree).

![demo](demo.png)

## Features

- **Side-by-side View**: List of all worktrees on the left, and instant Git Diff on the right.
- **Auto Refresh**: The worktree list and status are automatically updated every 2 seconds.
- **Syntax Highlighting**: Beautifully formatted diffs powered by [Rich](https://github.com/Textualize/rich).
- **Interactive Management**:
  - `a`: Add a new worktree with a modal dialog.
  - `r`: Remove the selected worktree with a confirmation prompt.
  - `R`: Manually refresh the view.
  - `?`: Show help information.

## Installation

```bash
pip install easy-worktree-tui
```

Make sure you have `easy-worktree` installed and initialized in your repository.

## Usage

Simply run:

```bash
wtt
```

## Keybindings

| Key | Action |
| --- | --- |
| `j` / `Up` | Select previous worktree |
| `k` / `Down` | Select next worktree |
| `a` | Add a new worktree |
| `r` | Remove selected worktree |
| `R` | Refresh everything |
| `?` | Show help |
| `q` | Quit |

## License

MIT
