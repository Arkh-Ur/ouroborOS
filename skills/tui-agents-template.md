---
name: tui-agents-template
description: AGENTS.md template for OpenCode and Antigravity CLI. Copy the content below to the root of a TUI project (HyprCollab, or any Rust/Python/Go/Tauri app) so agents load TUI framework rules automatically as passive context.
---

# AGENTS.md Template for TUI Projects

Copy the block below as `AGENTS.md` to the root of your target project (e.g., HyprCollab).
OpenCode and Antigravity CLI load this file automatically on startup.

---

```markdown
# Agent System Context — TUI Project

You are a specialist TUI developer on this project. Components may be written in
Rust (Ratatui), Python (Textual), Go (Bubble Tea v2), or React/Tauri (Web TUI).

## Universal Rules

- Separate state, rendering, and events into distinct files for every framework.
- Use the ecosystem component library before building any widget from scratch.
- All I/O must be async — never block the rendering loop.

## Rust (Ratatui v0.30.0+)

- Use `ratatui::init()` / `ratatui::restore()` — never the legacy `Terminal::new(CrosstermBackend)`.
- Files: `app.rs` (state), `ui.rs` (render), `update.rs` (events).
- `ratatui::restore()` must be called on all exit paths including panics.
- For text input: `tui-textarea` crate. Never capture keystrokes manually.

## Python (Textual)

- All event handlers must be `async`.
- All styles go in an external `.tcss` file — zero inline styles in Python.
- Long-running tasks: `Worker` API (`self.run_worker()`), never `asyncio.create_task`.
- Use built-in widgets (`DataTable`, `Tree`, `RichLog`, etc.) before building custom ones.

## Go (Bubble Tea v2)

- Import from `charm.land/bubbletea/v2` — NOT `github.com/charmbracelet/bubbletea`.
- Bubbles: `charm.land/bubbles/v2/<component>`.
- `View()` must return `tea.View`, not `string`.
- Key events are `tea.KeyPressMsg`, not `tea.KeyMsg`.
- Never mutate the model outside of `Update()`.

## React / Tauri (Web TUI)

- `font-mono` only. Never `font-sans` or `font-serif`.
- `rounded-none` everywhere. No `shadow-*` classes.
- `caret-transparent` on all inputs. Block cursor `█` with `animate-pulse`.
- Borders: 1px solid `border-gray-600` or ASCII box-drawing characters.
- Sidebars closed by default.
- IPC: `invoke()` from `@tauri-apps/api/core` — never fetch to localhost.
- State: Zustand or Context — never Redux.

Read `DESIGN.md` in the project root before generating any visual component.
```
