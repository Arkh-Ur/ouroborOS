---
name: tui-textual
description: Build terminal UIs in Python using Textual. Use when working on Python TUI apps with textual, async widgets, TCSS styling, or interactive terminal applications in Python.
---

# Textual TUI — Python

## Architecture Rules

- All event handlers (`on_*` methods) must be `async`/`await`
- All styles go in an external `.tcss` file — zero inline styles in Python code
- `CSS_PATH` must point to the `.tcss` file in the App class
- Use `reactive()` for state that should trigger automatic re-renders
- Background/long-running tasks: `Worker` API (`self.run_worker(...)`) — never `asyncio.create_task` directly

```python
from textual.app import App, ComposeResult
from textual.reactive import reactive

class MyApp(App):
    CSS_PATH = "app.tcss"
    
    count: reactive[int] = reactive(0)
    
    def compose(self) -> ComposeResult:
        yield MyWidget()
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        self.count += 1
```

## Built-in Widgets (40+)

| Category | Widgets |
|---|---|
| Input | Button, Checkbox, Input, MaskedInput, RadioButton, RadioSet, Select, Switch, TextArea |
| Display | Label, Static, Rule, Sparkline, ProgressBar, LoadingIndicator |
| Containers | ListView, OptionList, SelectionList, DataTable, Tree, DirectoryTree, TabbedContent |
| Specialized | MarkdownViewer, RichLog, Log, Toast, Collapsible, ContentSwitcher |

Never reinvent these. If a built-in widget fits, use it.

## Worker API (Background Tasks)

```python
from textual.worker import Worker

class MyApp(App):
    def on_mount(self) -> None:
        self.run_worker(self.fetch_data(), exclusive=True)
    
    async def fetch_data(self) -> None:
        # Long-running async operation
        result = await some_api_call()
        self.query_one(DataTable).add_row(*result)
    
    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state == WorkerState.ERROR:
            self.notify(str(event.worker.error), severity="error")
```

For periodic polling: `self.set_interval(seconds, callback)`.

## TCSS Styling

```css
/* app.tcss */
Screen {
    layout: horizontal;
}

#sidebar {
    width: 20;
    border: solid $accent;
}

#main {
    width: 1fr;
    padding: 1 2;
}

DataTable {
    height: 100%;
}
```

Never put styles inside Python widget definitions unless you're setting a `DEFAULT_CSS` class variable as a fallback.

## Lifecycle

```
compose() → mounting → event handling → rendering
```

Query the DOM with `self.query_one(WidgetType)` or `self.query("#id")`.

## Decision Gates

| Need | Solution |
|---|---|
| Editable table | `DataTable` |
| Hierarchical tree | `Tree` or `DirectoryTree` |
| Polling external data | `Worker` API + `set_interval` |
| Multi-panel layout | `Horizontal`/`Vertical` containers in `.tcss` |
| Markdown rendering | `MarkdownViewer` |
| Realtime logs | `RichLog` |
| Testing | `pytest` + `textual.testing.Pilot` |

## Testing Pattern

```python
from textual.testing import Pilot

async def test_button_click(app: MyApp) -> None:
    async with app.run_test() as pilot:
        await pilot.click("#submit-button")
        assert app.query_one(Label).renderable == "Done"
```

## Output Contract

- Runnable with `python -m app` or `textual run app.py`
- External `.tcss` file exists alongside the Python module
- Zero inline styles in Python code
- All event handlers are `async`
- Long-running tasks use `Worker` API, never raw `asyncio`
