from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, ListView, ListItem, Label, Static, Input, Button, Tree, TextArea
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.binding import Binding
from textual.reactive import reactive
from textual.screen import ModalScreen
from rich.syntax import Syntax
import subprocess
import os
from pathlib import Path

import sys
from importlib.metadata import version as get_version

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
    def __init__(self, wt_name: str):
        super().__init__()
        self.wt_name = wt_name

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-content"):
            yield Label(f"Remove worktree '{self.wt_name}'?", id="modal-title")
            with Horizontal(id="modal-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Remove", variant="error", id="remove")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "remove")

class WorktreeListItem(ListItem):
    def __init__(self, name: str, branch: str, path: str, status: str):
        super().__init__()
        self.wt_name = name
        self.branch = branch
        self.path = path
        self.status = status
        self.label = Label(f"{name:<15} {branch:<15} {status}")

    def compose(self) -> ComposeResult:
        yield self.label

import re

def strip_ansi(text: str) -> str:
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

class EasyWorktree(App):
    CSS = """
    Screen {
        background: $surface;
    }
    #side-menu {
        width: 30;
        height: 100%;
        border-right: tall #333333;
        background: $surface;
    }
    #file-tree-container {
        width: 30;
        height: 100%;
        border-right: tall #333333;
        background: $surface;
    }
    #main-panel {
        width: 1fr;
        height: 100%;
        padding: 0;
    }
    #diff-view {
        height: 100%;
        border-top: solid #333333;
        background: $boost;
    }
    #menu-title, #file-title, #diff-title {
        background: #2a2a2a;
        color: #888888;
        padding: 0 1;
        height: 1;
        text-style: bold;
        width: 100%;
    }
    #file-tree {
        height: 100%;
        background: $surface;
    }
    #file-tree:focus > .tree--cursor {
        background: $primary;
        color: $text;
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
    #worktree-list:focus > ListItem.--highlight {
        background: $primary;
        color: $text;
    }
    #worktree-list > ListItem.--highlight {
        background: $primary-darken-2;
        color: $text-muted;
    }
    #worktree-list > ListItem:hover {
        background: $boost;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("?", "help", "Help", show=True),
        Binding("a", "add_worktree", "Add WT", show=True),
        Binding("r", "remove_worktree", "Remove WT", show=True),
        Binding("R", "refresh", "Refresh", show=True),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("tab", "switch_focus_forward", "Next Pane", show=False),
        Binding("shift+tab", "switch_focus_backward", "Prev Pane", show=False),
        Binding("l", "switch_focus_forward", "→", show=False),
        Binding("h", "switch_focus_backward", "←", show=False),
    ]

    selected_path = reactive("")
    selected_file = reactive("")

    def __init__(self, git_dir: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.git_dir = git_dir
        # --git-dir=xxx を wt コマンドの先頭に付けるプレフィックス
        self.wt_prefix = [f"--git-dir={git_dir}"] if git_dir else []

    def _wt(self, *args) -> list[str]:
        """wt コマンドを git_dir オプション付きで作成する"""
        return ["wt"] + self.wt_prefix + list(args)

    def compose(self) -> ComposeResult:
        title = f"🌳 {'[' + self.git_dir + ']' if self.git_dir else 'Easy Worktree'}"
        yield Header()
        with Horizontal():
            with Vertical(id="side-menu"):
                yield Label(title, id="menu-title")
                yield ListView(id="worktree-list")
            with Vertical(id="file-tree-container"):
                yield Label("📁 Files", id="file-title")
                yield Tree("Changes", id="file-tree")
            with Vertical(id="main-panel"):
                yield Label("📄 Git Diff", id="diff-title")
                yield TextArea(id="diff-view", read_only=True, language="diff")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#worktree-list", ListView).focus()
        self.refresh_list()
        self.set_interval(2, self.refresh_list)

    @work(exclusive=True, thread=True)
    def refresh_list(self) -> None:
        try:
            # wt list の結果を取得
            result = subprocess.run(self._wt("list"), capture_output=True, text=True, check=True)
            output = strip_ansi(result.stdout.strip())
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
                path_result = subprocess.run(self._wt("co", name), capture_output=True, text=True)
                raw_path = path_result.stdout.strip()
                
                if not raw_path:
                    continue

                # Ensure path is absolute
                path = str(Path(raw_path).absolute())
                
                if not os.path.exists(path):
                    # Try relative to the current working directory as fallback
                    path = str(Path(os.getcwd()) / raw_path)
                    if not os.path.exists(path):
                        continue

                # status (changes) is often at the end, but let's just grab what's left
                status = " ".join(parts[2:])
                
                worktrees.append((name, branch, path, status))

            # UI Update on main thread
            self.call_from_thread(self.update_list_ui, worktrees)

        except subprocess.CalledProcessError as e:
            self.app.call_from_thread(self.notify, f"wt list failed: {e.stderr}", severity="error")
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Refresh error: {str(e)}", severity="error")

    def update_list_ui(self, worktrees: list) -> None:
        list_view = self.query_one("#worktree-list", ListView)
        
        # Check if content actually changed to avoid flicker/highlight loss
        current_wts = []
        for child in list_view.children:
            if hasattr(child, "wt_name"):
                current_wts.append((child.wt_name, child.branch, child.path, child.status))
        
        if current_wts == worktrees:
            # If no functional changes, don't clear and rebuild
            return

        # Save current selection
        selected_wt = None
        if list_view.highlighted_child:
            selected_wt = getattr(list_view.highlighted_child, "wt_name", None)
            
        # Clear and rebuild
        list_view.clear()
        new_index = 0
        for i, (name, branch, path, status) in enumerate(worktrees):
            item = WorktreeListItem(name, branch, path, status)
            list_view.append(item)
            if name == selected_wt:
                new_index = i
        
        # Restore selection
        if worktrees:
            list_view.index = new_index
            
        # Ensure focus is maintained
        if not self.focused:
             list_view.focus()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and hasattr(event.item, 'path'):
            self.selected_path = event.item.path
            self.selected_file = ""
            self.update_file_tree()
            self.update_diff()

    @work(exclusive=True, thread=True)
    def update_file_tree(self) -> None:
        if not self.selected_path:
            return
        
        try:
            # 1. Get tracked changed files
            diff_result = subprocess.run(
                ["git", "diff", "--name-status", "HEAD"], 
                cwd=self.selected_path, capture_output=True, text=True
            )
            # 2. Get untracked files
            untracked_result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=self.selected_path, capture_output=True, text=True
            )
            
            files = []
            if diff_result.stdout:
                for line in diff_result.stdout.strip().splitlines():
                    if line:
                        parts = line.split(maxsplit=1)
                        if len(parts) == 2:
                            status, path = parts
                            files.append((path, status))
                            
            if untracked_result.stdout:
                for line in untracked_result.stdout.strip().splitlines():
                    if line:
                        files.append((line, "?"))
                        
            # Sort files
            files.sort(key=lambda x: x[0])
            self.call_from_thread(self._render_file_tree, files)
        except Exception as e:
            pass

    def _render_file_tree(self, files: list[tuple[str, str]]) -> None:
        tree = self.query_one("#file-tree", Tree)
        tree.clear()
        
        if not files:
            tree.root.set_label("No changes")
            return
        else:
            tree.root.set_label("Changes")
            tree.root.expand()
            
        # Build dict structure
        tree_dict = {}
        for path, status in files:
            parts = Path(path).parts
            current = tree_dict
            for p in parts[:-1]:
                if p not in current:
                    current[p] = {}
                current = current[p]
            current[parts[-1]] = (path, status)
            
        def add_nodes(node, structure):
            keys = sorted(structure.keys(), key=lambda k: (not isinstance(structure[k], tuple), k))
            for k in keys:
                if isinstance(structure[k], dict):
                    child = node.add(k, expand=True)
                    add_nodes(child, structure[k])
                else:
                    path, status = structure[k]
                    label = f"[{status}] {k}" if status != "?" else f"[?] {k}"
                    node.add_leaf(label, data=path)
                    
        add_nodes(tree.root, tree_dict)

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        if event.node and event.node.data:
            self.selected_file = event.node.data
        else:
            self.selected_file = ""
        self.update_diff()

    def update_diff(self) -> None:
        if not self.selected_path:
            return
        
        try:
            if self.selected_file:
                # Diff for specific file
                diff_cmd = ["git", "diff", "HEAD", "--color=never", "--", self.selected_file]
                diff_result = subprocess.run(diff_cmd, cwd=self.selected_path, capture_output=True, text=True)
                diff_content = diff_result.stdout
                
                if not diff_content:
                    untracked_cmd = ["git", "ls-files", "--others", "--exclude-standard", self.selected_file]
                    untracked_res = subprocess.run(untracked_cmd, cwd=self.selected_path, capture_output=True, text=True)
                    if untracked_res.stdout.strip() == self.selected_file:
                        file_path = Path(self.selected_path) / self.selected_file
                        if file_path.exists():
                            try:
                                diff_content = f"Untracked file: {self.selected_file}\n\n" + file_path.read_text(errors="replace")
                            except Exception:
                                diff_content = "Binary or unreadable file."
                        else:
                            diff_content = "File not found or empty."
                    else:
                        diff_content = "No changes."
            else:
                diff_result = subprocess.run(
                    ["git", "diff", "--color=never"], 
                    cwd=self.selected_path, 
                    capture_output=True, 
                    text=True
                )
                diff_content = diff_result.stdout or "No changes."

            diff_view = self.query_one("#diff-view", TextArea)
            diff_view.text = diff_content
        except Exception as e:
            self.query_one("#diff-view", TextArea).text = f"Error: {e}"

    def action_switch_focus_forward(self) -> None:
        panes = [
            self.query_one("#worktree-list"),
            self.query_one("#file-tree"),
            self.query_one("#diff-view")
        ]
        active = self.focused
        if active in panes:
            idx = panes.index(active)
            panes[(idx + 1) % len(panes)].focus()
        else:
            panes[1].focus() # Focus file tree by default if we tab from elsewhere

    def action_switch_focus_backward(self) -> None:
        panes = [
            self.query_one("#worktree-list"),
            self.query_one("#file-tree"),
            self.query_one("#diff-view")
        ]
        active = self.focused
        if active in panes:
            idx = panes.index(active)
            panes[(idx - 1) % len(panes)].focus()
        else:
            panes[0].focus()

    def action_refresh(self) -> None:
        self.refresh_list()

    def action_cursor_down(self) -> None:
        self.query_one("#worktree-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#worktree-list", ListView).action_cursor_up()

    def action_help(self) -> None:
        self.notify("Worktree 管理 TUI\n\na: Add WT\nr: Remove WT\nR: Refresh\nq: Quit", title="Help")

    def action_add_worktree(self) -> None:
        def handle_add(result: str):
            if result:
                try:
                    parts = result.split()
                    cmd = self._wt("add", *parts)
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
                        subprocess.run(self._wt("rm", item.wt_name), check=True)
                        self.notify(f"Removed worktree: {item.wt_name}")
                        self.refresh_list()
                    except subprocess.CalledProcessError as e:
                        self.notify(f"Failed to remove: {e}", severity="error")

            self.push_screen(ConfirmRemoveModal(item.wt_name), handle_remove)

def main():
    args = sys.argv[1:]

    if "--version" in args or "-v" in args:
        try:
            print(f"easy-worktree-tui version {get_version('easy-worktree-tui')}")
        except Exception:
            print("easy-worktree-tui version unknown")
        return

    # --git-dir=xxx 形式を探してアプリに渡す
    git_dir = None
    remaining = []
    for arg in args:
        if arg.startswith("--git-dir="):
            git_dir = arg[len("--git-dir="):]
        else:
            remaining.append(arg)

    app = EasyWorktree(git_dir=git_dir)
    app.run()

if __name__ == "__main__":
    main()
