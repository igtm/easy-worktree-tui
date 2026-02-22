from textual.app import App, ComposeResult
from textual.widgets import RichLog, TextArea, Static
from rich.syntax import Syntax

class TestApp(App):
    def compose(self) -> ComposeResult:
        # yield RichLog(id="log")
        yield TextArea("diff content here", id="ta", language="diff")

    def on_mount(self) -> None:
        # log = self.query_one(RichLog)
        # log.write(Syntax("foo = 1\nbar = 2", "python"))
        pass

if __name__ == "__main__":
    app = TestApp()
    print("TextArea imports fine")
