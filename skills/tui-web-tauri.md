---
name: tui-web-tauri
description: Build React/Tailwind UIs inside Tauri that look and behave exactly like terminal applications. Use when working on HyprCollab, Web TUI components, fake-terminal UIs in Tauri, or any React UI that must simulate a terminal aesthetic.
---

# Web TUI — React + Tauri v2

## Aesthetic Rules — Never Violate

These rules simulate a pure terminal / tiling window manager aesthetic in a WebView context.

| Rule | What it means |
|---|---|
| `font-mono` only | Never `font-sans` or `font-serif` |
| `rounded-none` everywhere | No `rounded-lg`, `rounded-md`, `rounded-sm`, etc. |
| No shadows | No `shadow-*` classes of any kind |
| `caret-transparent` on inputs | Hide the native browser text caret |
| Block cursor | Simulate with `█` character + `animate-pulse` |
| 1px borders | `border border-gray-600` or ASCII box-drawing characters |
| Hidden scrollbars | Use `scrollbar-hide` plugin or `overflow-hidden` + JS scroll |
| Bracketed buttons | `[ Action ]` text; hover = invert fg/bg |
| Sidebars closed by default | Never open on initial load |
| Input prompt style | `> ` prefix with block cursor |

Read `DESIGN.md` in the project root before generating any component.

## ASCII Box-Drawing Components

```tsx
// Terminal-style container border
function TerminalPane({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="font-mono text-sm">
      <div className="text-gray-400">┌─ {title} {'─'.repeat(40)}</div>
      <div className="border-l border-r border-gray-600 px-2 py-1">
        {children}
      </div>
      <div className="text-gray-400">{'└' + '─'.repeat(43)}</div>
    </div>
  );
}

// Terminal-style input with block cursor
function TerminalInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center gap-1 font-mono">
      <span className="text-green-400">&gt;</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-transparent border-none outline-none caret-transparent text-white font-mono flex-1"
      />
      <span className="animate-pulse text-white">█</span>
    </div>
  );
}

// Terminal-style button
function TerminalButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="font-mono text-gray-300 hover:bg-white hover:text-black px-1 transition-none"
    >
      [ {label} ]
    </button>
  );
}
```

## Tauri v2 IPC

```tsx
// Correct: use invoke() — never fetch to localhost
import { invoke } from '@tauri-apps/api/core';
import { appDataDir, join } from '@tauri-apps/api/path';

const result = await invoke<string>('my_command', { arg: 'value' });
const configPath = await join(await appDataDir(), 'config.json');
```

## Global State

Use Zustand or React Context. Never Redux.

```tsx
import { create } from 'zustand';

interface AppStore {
  activeAgent: string | null;
  conversations: Conversation[];
  setActiveAgent: (id: string) => void;
}

const useStore = create<AppStore>((set) => ({
  activeAgent: null,
  conversations: [],
  setActiveAgent: (id) => set({ activeAgent: id }),
}));
```

## Tauri v2 ACL Capabilities

Each window needs a capability in `src-tauri/capabilities/<name>.json`:

```json
{
  "identifier": "main-capability",
  "description": "Permissions for the main window",
  "windows": ["main"],
  "permissions": [
    "core:default",
    {
      "identifier": "fs:allow-read-text-file",
      "allow": [{ "path": "$APPDATA/*" }]
    }
  ]
}
```

- `windows`: array of window labels (supports glob `*`, `admin-*`)
- `permissions`: `"${plugin}:${permission}"` string or `{ identifier, allow, deny }` object
- `local: true` (default) — for local app URLs; `remote` only for external URLs (use with caution)

## Decision Gates

| Need | Terminal-equivalent solution |
|---|---|
| Text editor | `textarea` + `caret-transparent` + custom `█` cursor |
| Data table | `div` with `grid-cols-*` and `font-mono`, never `<table>` with web styles |
| Navigation menu | Text list with `>` active indicator |
| Modal / dialog | ASCII box-drawing centered on screen, not `Dialog` with `rounded-lg` |
| System data | `invoke()` to Rust backend |
| File paths | `@tauri-apps/api/path` helpers |

## Output Contract

- React component with Tailwind
- Zero `rounded-*` classes (except `rounded-none`)
- Zero `shadow-*` classes
- Zero `font-sans` or `font-serif`
- All `<input>` elements have `caret-transparent`
- Compatible with Tauri v2 WebView
- State via Zustand or Context, never Redux
