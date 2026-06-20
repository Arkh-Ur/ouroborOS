---
name: tui-bubbletea
description: Build terminal UIs in Go using Bubble Tea v2. Use when working on Go TUI apps with bubbletea, lipgloss, bubbles, or terminal applications in Go.
---

# Bubble Tea TUI — Go (v2)

## Import Paths (v2 — different from v1)

```go
import (
    tea "charm.land/bubbletea/v2"                  // NOT github.com/charmbracelet/bubbletea
    "charm.land/bubbles/v2/list"                    // NOT github.com/charmbracelet/bubbles/list
    "charm.land/bubbles/v2/textinput"
    "github.com/charmbracelet/lipgloss"             // lipgloss stays on github.com
)
```

## Elm Architecture — Strict

```go
// model.go
type Model struct {
    // all mutable state here
    list     list.Model
    input    textinput.Model
    quitting bool
}

func (m Model) Init() tea.Cmd {
    return textinput.Blink
}

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
    switch msg := msg.(type) {
    case tea.KeyPressMsg:                        // v2: KeyPressMsg, NOT KeyMsg
        switch msg.String() {
        case "ctrl+c", "q":
            return m, tea.Quit()
        }
    case tea.WindowSizeMsg:
        m.list.SetWidth(msg.Width)
    }
    // delegate to sub-models
    var cmd tea.Cmd
    m.list, cmd = m.list.Update(msg)
    return m, cmd
}

// view.go
func (m Model) View() tea.View {                 // v2: returns tea.View, NOT string
    return tea.View(m.list.View())
}
```

Never mutate the model outside of `Update()`. Never use goroutines that write to the model directly.

## v2 API Changes vs v1

| v1 | v2 |
|---|---|
| `tea.KeyMsg` | `tea.KeyPressMsg` |
| `View() string` | `View() tea.View` |
| `github.com/charmbracelet/bubbletea` | `charm.land/bubbletea/v2` |
| `github.com/charmbracelet/bubbles/list` | `charm.land/bubbles/v2/list` |

## Built-in Bubbles (v2)

| Package | Import path | Use |
|---|---|---|
| list | `charm.land/bubbles/v2/list` | Filterable list with pagination |
| textinput | `charm.land/bubbles/v2/textinput` | Single-line text input |
| textarea | `charm.land/bubbles/v2/textarea` | Multi-line text input |
| spinner | `charm.land/bubbles/v2/spinner` | Activity indicator |
| progress | `charm.land/bubbles/v2/progress` | Progress bar |
| table | `charm.land/bubbles/v2/table` | Scrollable table |
| viewport | `charm.land/bubbles/v2/viewport` | Scrollable text viewport |
| filepicker | `charm.land/bubbles/v2/filepicker` | File picker dialog |
| help | `charm.land/bubbles/v2/help` | Keybinding help view |
| key | `charm.land/bubbles/v2/key` | Definable keybindings |

## Built-in Commands

```go
tea.Quit()                      // clean exit
tea.Batch(cmd1, cmd2, cmd3)     // run concurrently
tea.Sequence(cmd1, cmd2)        // run sequentially
tea.Tick(duration, fn)          // timer independent of system clock
tea.Every(duration, fn)         // timer synced with system clock
tea.ExecProcess(cmd, callback)  // run external process
```

## File Structure

```
cmd/
└── myapp/
    └── main.go      ← tea.NewProgram(model, tea.WithAltScreen())
internal/
├── model.go         ← Model struct + Init() + Update()
├── view.go          ← View()
└── styles.go        ← Lipgloss palette centralized
```

Lipgloss styles must be defined once and referenced everywhere — never inline `lipgloss.NewStyle()` in `View()`.

## Debug

```go
// In main.go — stdout is occupied by the TUI
f, _ := tea.LogToFile("debug.log", "debug")
defer f.Close()
```

Never use `fmt.Println` or `log.Println` in a running TUI — it corrupts the terminal output.

## Decision Gates

| Need | Solution |
|---|---|
| Filterable list | `bubbles/v2/list` |
| Single-line input | `bubbles/v2/textinput` |
| Multi-line input | `bubbles/v2/textarea` |
| Progress bar | `bubbles/v2/progress` |
| Table with scroll | `bubbles/v2/table` |
| Long scrollable text | `bubbles/v2/viewport` |
| Async (HTTP, disk) | `tea.Cmd` returning a `tea.Msg` — never raw goroutines |
| Installer / config app | `list` + `textinput` + `progress` combined |
| Static binary (immutable OS) | `CGO_ENABLED=0 go build` |

## Output Contract

- `go build ./...` without errors
- Elm Architecture enforced: no model mutation outside `Update()`
- `View()` returns `tea.View` (v2 API)
- All async operations via `tea.Cmd`
- Lipgloss palette centralized in `styles.go`
- Correct v2 import paths (`charm.land/...`)
