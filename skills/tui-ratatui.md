---
name: tui-ratatui
description: Build terminal UIs in Rust using Ratatui. Use when working on Rust TUI apps with ratatui, crossterm, or terminal rendering in Rust.
---

# Ratatui TUI — Rust

## Initialization (v0.30.0+)

- `ratatui::init()` / `ratatui::restore()` — the modern API; handles raw mode, alternate screen, and panic hooks
- `ratatui::run()` — for simple apps (wraps init, loop, restore automatically)
- Never use the legacy pattern `Terminal::new(CrosstermBackend::new(stdout()))`

## File Architecture

```
src/
├── main.rs      ← ratatui::init() + run loop + ratatui::restore()
├── app.rs       ← App struct with all mutable state
├── ui.rs        ← draw(frame: &mut Frame, app: &App) — the ONLY function that touches Frame
└── update.rs    ← handle_events(&mut app) using crossterm::event
```

`ratatui::restore()` must be called on every exit path, including panics. Set up a panic hook:

```rust
let original_hook = std::panic::take_hook();
std::panic::set_hook(Box::new(move |panic_info| {
    ratatui::restore();
    original_hook(panic_info);
}));
```

## Layout Constraints

| Constraint | Use |
|---|---|
| `Length(n)` | Fixed size in terminal cells |
| `Min(n)` | Minimum size, expands if space available |
| `Max(n)` | Maximum size, shrinks if needed |
| `Fill(n)` | Proportional (like flex-grow) |
| `Percentage(n)` | Percentage of parent space |

Never hardcode pixel values. Always use constraints.

## Recommended Crates

| Crate | Purpose |
|---|---|
| `ratatui` | Main framework (includes `ratatui-widgets` + `ratatui-core`) |
| `crossterm` | Default backend, cross-platform |
| `tui-textarea` | Text input widget — never capture keystrokes manually |
| `ratatui-image` | Render images in the terminal |
| `throbber-widgets-tui` | Animated spinners |
| `tokio` | Async runtime for network/IO operations |

For widget crates that depend on the ratatui API: depend on `ratatui-core` for stability.

## Event Loop Pattern

```rust
// update.rs
pub fn handle_events(app: &mut App) -> io::Result<()> {
    if crossterm::event::poll(Duration::from_millis(16))? {
        match crossterm::event::read()? {
            Event::Key(key) if key.kind == KeyEventKind::Press => {
                match key.code {
                    KeyCode::Char('q') => app.quit = true,
                    // ...
                }
            }
            Event::Resize(_, _) => { /* handled by ratatui automatically */ }
            _ => {}
        }
    }
    Ok(())
}
```

Use `crossterm::event::poll` with a timeout — never blocking reads — so the render loop stays responsive.

## Decision Gates

| Need | Solution |
|---|---|
| Text input | `tui-textarea` crate |
| Async (network, file I/O) | `tokio` + `crossterm::event::poll` with timeout |
| Images in terminal | `ratatui-image` |
| Spinners / loading indicators | `throbber-widgets-tui` |
| Static binary (immutable OS) | `CGO_ENABLED=0` is Rust-irrelevant; use `--target x86_64-unknown-linux-musl` |

## Output Contract

- Compiles with `cargo build` without warnings
- `#[deny(unused_imports)]` in `main.rs`
- State, rendering, and event handling in separate files
- `ratatui::restore()` called on all exit paths including panics
- No blocking calls in the render path
