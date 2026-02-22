from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, ListView, ListItem, Label, Static, Input, Button
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.binding import Binding
from textual.reactive import reactive
from textual.screen import ModalScreen
from rich.syntax import Syntax
import subprocess
import os
from pathlib import Path

class AddWorktreeModal(ModalScreen[str]):
    def compose(self) -> ComposeResult:
        with Vertical(id="modal-content"):
            yield Label("Add Worktree", id="modal-title")
            yield Input(placeholder="Worktree name", id="wt-name")
            yield Input(placeholder="Base branch (optional)", id="base-branch")
            with Horizontal(id="modal-buttons"):
                yield Button("Cancel", variant="error", id="cancel")
                yield Button("Add", variant="success", id="add")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add":
            name = self.query_one("#wt-name", Input).value
            base = self.query_one("#base-branch", Input).value
            if name:
                self.dismiss(f"{name} {base}".strip())
        else:
            self.dismiss("")

class ConfirmRemoveModal(ModalScreen[bool]):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-content"):
            yield Label(f"Remove worktree '{self.name}'?", id="modal-title")
            with Horizontal(id="modal-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Remove", variant="error", id="remove")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "remove")

class WorktreeListItem(ListItem):
    def __init__(self, name: str, branch: str, path: str, status: str):
        super().__init__()
        self.name = name
        self.branch = branch
        self.path = path
        self.status = status
        self.label = Label(f"{name:<15} {branch:<15} {status}")

    def compose(self) -> ComposeResult:
        yield self.label

class EasyWorktreeApp(App):
    CSS = """
    Screen {
        background: $surface;
    }
    #side-menu {
        width: 45;
        height: 100%;
        border-right: tall $accent;
        background: $surface;
    }
    #main-panel {
        height: 100%;
        padding: 0;
    }
    #diff-container {
        height: 100%;
        border: solid $primary;
        background: $boost;
    }
    #menu-title {
        background: $accent;
        color: $text;
        text-align: center;
        text-style: bold;
        padding: 1;
    }
    #diff-title {
        background: $primary;
        color: $text;
        text-align: center;
        text-style: bold;
        padding: 1;
    }
    #modal-content {
        width: 60;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1;
        margin: 4 8;
    }
    #modal-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    #modal-buttons {
        margin-top: 1;
        align: center middle;
        height: 3;
    }
    #modal-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("?", "help", "Help", show=True),
        Binding("a", "add_worktree", "Add WT", show=True),
        Binding("r", "remove_worktree", "Remove WT", show=True),
        Binding("R", "refresh", "Refresh", show=True),
    ]

    selected_path = reactive("")

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="side-menu"):
                yield Label("🌳 Easy Worktree", id="menu-title")
                yield ListView(id="worktree-list")
            with Vertical(id="main-panel"):
                yield Label("📄 Git Diff", id="diff-title")
                with ScrollableContainer(id="diff-container"):
                    yield Static(id="diff-view", expand=True)
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_list()
        self.set_interval(2, self.refresh_list)

    def refresh_list(self) -> None:
        try:
            # wt list の結果を取得
            result = subprocess.run(["wt", "list"], capture_output=True, text=True, check=True)
            output = result.stdout.strip()
            if not output:
                return

            lines = output.splitlines()
            
            # Find the header separator line (---)
            separator_index = -1
            for i, line in enumerate(lines):
                if line.startswith("---") or "---" in line:
                    separator_index = i
                    break
            
            if separator_index == -1 or separator_index + 1 >= len(lines):
                return

            worktrees = []
            # Start from the line after the separator
            for line in lines[separator_index + 1:]:
                parts = line.split()
                if not parts:
                    continue
                
                # (main) -> main
                raw_name = parts[0]
                name = raw_name.strip("()")
                
                # branch is usually the second part
                branch = parts[1] if len(parts) > 1 else "unknown"
                
                # The path retrieval is the most reliable way to confirm it exists
                path_result = subprocess.run(["wt", "co", name], capture_output=True, text=True)
                path = path_result.stdout.strip()
                
                if not path:
                    continue

                # status (changes) is often at the end, but let's just grab what's left
                # Typically: Name Branch Created LastCommit Changes
                # We can't easily parse columns by index if values have spaces or are missing.
                # For now, let's just show what we have.
                status = " ".join(parts[2:])
                
                worktrees.append((name, branch, path, status))

            list_view = self.query_one("#worktree-list", ListView)
            current_index = list_view.index
            
            # Clear and rebuild
            list_view.clear()
            for name, branch, path, status in worktrees:
                list_view.append(WorktreeListItem(name, branch, path, status))
            
            if current_index is not None and current_index < len(worktrees):
                list_view.index = current_index
            elif worktrees and list_view.index is None:
                list_view.index = 0

        except subprocess.CalledProcessError as e:
            self.notify(f"wt list failed: {e.stderr}", severity="error")
        except Exception as e:
            self.notify(f"Refresh error: {str(e)}", severity="error")

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item:
            self.selected_path = event.item.path
            self.update_diff()

    def update_diff(self) -> None:
        if not self.selected_path:
            return
        
        try:
            diff_result = subprocess.run(
                ["git", "diff", "--color=never"], 
                cwd=self.selected_path, 
                capture_output=True, 
                text=True
            )
            diff_content = diff_result.stdout or "No changes."
            syntax = Syntax(diff_content, "diff", theme="monokai", line_numbers=True)
            diff_view = self.query_one("#diff-view", Static)
            diff_view.update(syntax)
        except Exception as e:
            self.query_one("#diff-view", Static).update(f"Error: {e}")

    def action_refresh(self) -> None:
        self.refresh_list()
        self.update_diff()

    def action_help(self) -> None:
        self.notify("Worktree 管理 TUI\n\na: Add WT\nr: Remove WT\nR: Refresh\nq: Quit", title="Help")

    def action_add_worktree(self) -> None:
        def handle_add(result: str):
            if result:
                try:
                    parts = result.split()
                    cmd = ["wt", "add"] + parts
                    subprocess.run(cmd, check=True)
                    self.notify(f"Added worktree: {parts[0]}")
                    self.refresh_list()
                except subprocess.CalledProcessError as e:
                    self.notify(f"Failed to add: {e}", severity="error")

        self.push_screen(AddWorktreeModal(), handle_add)

    def action_remove_worktree(self) -> None:
        list_view = self.query_one("#worktree-list", ListView)
        if list_view.highlighted_child:
            item = list_view.highlighted_child
            def handle_remove(confirmed: bool):
                if confirmed:
                    try:
                        subprocess.run(["wt", "rm", item.name], check=True)
                        self.notify(f"Removed worktree: {item.name}")
                        self.refresh_list()
                    except subprocess.CalledProcessError as e:
                        self.notify(f"Failed to remove: {e}", severity="error")

            self.push_screen(ConfirmRemoveModal(item.name), handle_remove)

def main():
    app = EasyWorktreeApp()
    app.run()

if __name__ == "__main__":
    main()
