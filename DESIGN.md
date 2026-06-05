# Design System: Terminal Aesthetic

> Copy this file to the root of any project that requires a Web TUI aesthetic (e.g., HyprCollab).
> Claude Code, OpenCode, and Antigravity CLI will load it automatically as system context.

---

## Core Principle

This project enforces a pure terminal / tiling window manager aesthetic across all UI components. The UI is rendered in a web context (React/Tauri WebView) but MUST look, feel, and behave like a native terminal application running in a modern Linux tiling environment (Hyprland, i3, sway).

**No web UI paradigms. No SaaS aesthetics.**

---

## Absolute Rules — Never Violate

| Property | Rule |
|---|---|
| **Font** | `font-mono` only. Never `font-sans` or `font-serif`. |
| **Borders** | `rounded-none`. No rounded corners of any kind (`rounded-lg`, `rounded-md`, etc. are forbidden). |
| **Shadows** | None. No `shadow-*` classes. |
| **Input cursors** | `caret-transparent`. Block cursor `█` with `animate-pulse` or CSS `@keyframes blink`. |
| **Border style** | 1px solid `border-gray-600` OR ASCII box-drawing characters (`┌ ┐ └ ┘ │ ─`). |
| **Scrollbars** | Hidden. Use `scrollbar-hide` Tailwind plugin or `overflow: hidden` with JS scroll. |
| **Buttons** | Bracketed text `[ Action ]`. Hover state = invert fg/bg (`bg-white text-black`). |
| **Sidebars** | Closed by default on initial load. Toggle explicitly. |
| **Gradients** | Forbidden. Flat colors only. |

---

## Component Patterns

| Web pattern | Terminal equivalent |
|---|---|
| `<input>` with browser caret | `> ` prompt prefix + `█` block cursor via `caret-transparent` |
| `<button class="rounded-lg">` | `[ Label ]` text — hover inverts colors |
| Modal / Dialog with `rounded-lg` | ASCII box-drawing frame centered on screen |
| Navigation bar with icons | Text list with `>` active indicator |
| Data table with default styles | `div` grid with `font-mono` column alignment |
| Sidebar with shadow | Collapsible pane, `border-r border-gray-600`, hidden by default |
| Toast notification | Inline status line or top-bar message in `[ INFO ]` format |

---

## Color Guidance

No fixed palette is enforced here — set your project palette in a separate tokens file. Defaults:

```css
--bg:        #0d0d0d  /* near-black background */
--fg:        #e0e0e0  /* light gray text */
--border:    #404040  /* subtle border */
--accent:    #4ade80  /* terminal green for prompts / active states */
--muted:     #6b7280  /* gray for secondary text */
--error:     #f87171  /* red for errors */
```

---

## Tauri-Specific Rules

- IPC: `import { invoke } from '@tauri-apps/api/core'` — never fetch to localhost
- File paths: `import { appDataDir, join } from '@tauri-apps/api/path'`
- Global state: Zustand or React Context — never Redux
- Capabilities: define in `src-tauri/capabilities/<name>.json` per window

---

## Anti-Patterns (Explicit Prohibition)

Any component with the following must be refactored:

- `rounded-sm`, `rounded-md`, `rounded-lg`, `rounded-xl`, `rounded-2xl`, or `rounded-full`
- `shadow`, `shadow-sm`, `shadow-md`, `shadow-lg`, `shadow-xl`, or `drop-shadow-*`
- `font-sans`, `font-serif`, or any non-monospace font
- Native browser scrollbars visible
- Native browser text caret visible inside inputs
