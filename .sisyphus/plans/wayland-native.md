# Edgeware++ — Native Wayland (niri) Port

**Owner:** Ondine
**Author:** Sisyphus
**Status:** Draft (pre-Momus review)
**Date:** 2026-05-16

---

## 1. Decisions (locked, from user)

| # | Decision | Value |
|---|---|---|
| D1 | Strategy | **Option A** — keep app architecture, replace Tk only for compositor-coupled surfaces; keep Tk fallback for X11/other compositors |
| D2 | Compositor scope | **niri only** for the Wayland-native code path. Other Wayland compositors (sway/hyprland/kwin/mutter) keep the current XWayland behavior. |
| D3 | Toolkit | **GTK4 + [`gtk4-layer-shell`](https://github.com/wmww/gtk4-layer-shell)** via PyGObject. Hard new runtime dependency on the Wayland code path. |
| D4 | Config UI | **Also port to GTK4.** No layer-shell needed — it's a regular toplevel window. |
| D5 | niri integration | Ship a **separate `.kdl` file** (`edgeware.kdl`) the installer drops next to the user's `config.kdl`. User adds one `include` line. |

---

## 2. Goals & Non-Goals

### Goals
- G1: Popups (image/video/subliminal), prompt, splash render as **native Wayland surfaces** on niri — no XWayland for these.
- G2: Always-on-top, per-output placement, click-through, transparency work **correctly under niri** without window-rule hacks.
- G3: Global panic hotkey works **system-wide** under niri (today it silently fails outside XWayland focus).
- G4: Config window runs as a **native GTK4 Wayland window**.
- G5: X11 / non-niri-Wayland users see **zero regression** — Tk path stays untouched.
- G6: mpv video popups render via Wayland GPU context, no XWayland XID embedding.

### Non-Goals
- N1: Wayland support for sway/hyprland/kwin/mutter as a first-class path. They keep XWayland (Tk).
- N2: Replacing Tk in the runtime engine (`main_edgeware.py`'s root `Tk()` — see §6 for what stays).
- N3: Wayland-native panic-key capture protocol design. We use niri's built-in keybind → spawn IPC.
- N4: Per-pixel shaped windows / arbitrary masks on Wayland. Rectangular surfaces only.
- N5: Porting macOS or Windows code paths.

---

## 3. Surface inventory — what changes, what doesn't

### 3.1 Tk windows that need a Wayland-native replacement (engine)
Each is a `Toplevel` subclass that depends on `-topmost`, geometry, borderless, alpha, or click-through:

| File | Class | Layer-shell role |
|---|---|---|
| [`features/popup.py`](file:///home/ondine/.local/share/edgeware/src/features/popup.py) | `Popup` (base) | `OVERLAY`, top-anchored, exclusive zone 0 |
| [`features/image_popup.py`](file:///home/ondine/.local/share/edgeware/src/features/image_popup.py) | `ImagePopup` | content widget inside popup |
| [`features/video_popup.py`](file:///home/ondine/.local/share/edgeware/src/features/video_popup.py) | `VideoPopup` | content widget inside popup |
| [`features/subliminal_popup.py`](file:///home/ondine/.local/share/edgeware/src/features/subliminal_popup.py) | `SubliminalPopup` | `OVERLAY`, centered |
| [`features/startup_splash.py`](file:///home/ondine/.local/share/edgeware/src/features/startup_splash.py) | `StartupSplash` | `OVERLAY` (covers everything during init), centered |
| [`features/prompt.py`](file:///home/ondine/.local/share/edgeware/src/features/prompt.py) | `Prompt` | `OVERLAY`, centered, keyboard interactive |
| [`features/video_player.py`](file:///home/ondine/.local/share/edgeware/src/features/video_player.py) | `VideoPlayer` (Tk `Label` w/ mpv embed) | content widget; rewrite for `GtkGLArea` + `mpv-render` |

### 3.2 Tk OS-abstraction shims that need a Wayland branch
- [`os_utils/linux.py`](file:///home/ondine/.local/share/edgeware/src/os_utils/linux.py) → `set_borderless`, `set_clickthrough`. Currently no-op or X11-dependent on Wayland.

### 3.3 Tk-coupled monitor/coord code
- [`utils.py`](file:///home/ondine/.local/share/edgeware/src/utils.py) → `primary_monitor`, `random_monitor` use `screeninfo` (Xlib under the hood). Needs a GDK-based Wayland implementation.
- [`features/popup.py::compute_geometry`](file:///home/ondine/.local/share/edgeware/src/features/popup.py#L76-L141) uses absolute global coords. On Wayland, "place at output X" means anchoring the layer surface to that specific output's `GdkMonitor`, and using **monitor-local coords** inside.

### 3.4 Config UI (separate `main_config.py` process)
- [`config/window/__init__.py`](file:///home/ondine/.local/share/edgeware/src/config/window/__init__.py) — 290 lines, main config window + dialogs (2 `Toplevel`s for sub-dialogs).
- [`config/window/utils.py`](file:///home/ondine/.local/share/edgeware/src/config/window/utils.py) — shared widgets, key-listener dialogs.
- 13 tab files in [`config/window/tabs/`](file:///home/ondine/.local/share/edgeware/src/config/window/tabs) (~2,300 LOC total across tabs).
- [`config/window/widgets/`](file:///home/ondine/.local/share/edgeware/src/config/window/widgets) — custom Tk widgets (`scroll_frame.py`, `layout.py`).
- Theme system in [`config/themes.py`](file:///home/ondine/.local/share/edgeware/src/config/themes.py) is Tk-color-tuple based; GTK port uses CSS.

### 3.5 Stays on Tk forever (do not touch)
- `main_edgeware.py` root `Tk()` — kept **purely as the event loop / `.after()` scheduler**. No visible Tk windows. `root.withdraw()` already hides it. The Wayland popups will use GLib `MainContext` and we bridge with [`gbulb`](https://github.com/beeware/gbulb) or a thread, see §8.
  - **Alternative considered:** drop Tk entirely and use GLib's main loop as the only loop. **Rejected** because the engine uses `root.after(...)` ~12 places (scheduling, fade-out, hibernate timing, panic dispatch). Migration risk too high for Phase 1.
- Audio (`features/audio.py`), drive fill, corruption, scripting, IPC panic — none of these touch the display server.
- `panic.py`'s `simpledialog.askstring` for the lockout password — for v1, keep Tk. Phase 4 may swap for GTK.

### 3.6 Inventory of Tk-specific calls that must be replaced
From grep:
- `attributes("-topmost", True)` → 4 popup classes + key listener (config)
- `attributes("-alpha", X)` → 3 places (popup base, splash, subliminal); animated fade-out in popup
- `wm_attributes("-transparentcolor", ...)` → 1 (subliminal, Windows-only branch — keep)
- `overrideredirect(True)` → 1 (`os_utils/linux.py` KDE branch)
- `attributes("-type", "normal"/"splash")` → 2 (niri / generic Linux)
- `wait_visibility()` → 2 (popup pre-clickthrough, video player pre-mpv-embed)
- `winfo_id()` → 2 (video player → mpv `wid=`, used to be the only way to embed)
- `geometry(f"...+x+y")` → multiple (popup base, splash, prompt, subliminal)

All of these go away on the Wayland path. New code uses: `gtk4_layer_shell.set_layer(OVERLAY)`, `set_anchor()`, `set_namespace()`, `set_keyboard_mode()`, `Gtk.Widget.set_opacity()`, `GdkSurface.set_input_region(empty_region)`, and per-`GdkMonitor` placement.

---

## 4. Architecture

### 4.1 Backend abstraction

New module: `src/os_utils/backend.py`

```python
class WindowBackend(Protocol):
    """Compositor-coupled window operations. One implementation per display server."""

    def make_overlay(self, *, monitor, width, height, x, y,
                     keyboard: bool, opacity: float) -> "OverlayWindow": ...
    def make_centered_overlay(self, *, monitor, content_size_hint,
                              keyboard: bool, opacity: float) -> "OverlayWindow": ...
    def list_monitors(self) -> list[MonitorInfo]: ...
    def shutdown(self) -> None: ...

class OverlayWindow(Protocol):
    """Display-server-agnostic handle returned by the backend."""
    def set_content(self, widget) -> None: ...   # type depends on backend
    def set_clickthrough(self, on: bool) -> None: ...
    def set_opacity(self, alpha: float) -> None: ...
    def move(self, x: int, y: int) -> None: ...  # monitor-local on Wayland
    def close(self) -> None: ...
    # event bindings:
    def on_close(self, fn) -> None: ...
    def on_key(self, fn) -> None: ...
    def on_click(self, fn) -> None: ...
```

Two implementations:

- `TkBackend` in `src/os_utils/backend_tk.py` — wraps current Tk `Toplevel` behavior. Used on Windows, macOS, X11, and Wayland-non-niri.
- `NiriBackend` in `src/os_utils/backend_niri.py` — GTK4 + `gtk4-layer-shell`. Used only when `is_niri_wayland()` returns true.

Selection in `os_utils/__init__.py`:

```python
def make_backend() -> WindowBackend:
    if is_linux() and is_wayland() and compositor() == "niri":
        try:
            from os_utils.backend_niri import NiriBackend
            return NiriBackend()
        except ImportError as e:
            logging.warning(f"GTK4 layer-shell unavailable, falling back to Tk: {e}")
    from os_utils.backend_tk import TkBackend
    return TkBackend()
```

`compositor()` already partially exists (see `linux_utils.get_desktop_environment`); we add a `wayland_compositor()` helper that checks `XDG_CURRENT_DESKTOP=niri`, then `pgrep niri`.

### 4.2 Popup refactor

Current `Popup(Toplevel)` mixes:
1. Window-shell concerns (topmost, borderless, opacity, placement, clickthrough, fade-out, move animation).
2. Content concerns (caption, denial text, corruption-dev overlay, close button, multi-click logic, timeout, mitosis trigger, blacklist).

Refactor splits these:

```
Popup (no Tk inheritance) — orchestration, has-a OverlayWindow
  ├── window: OverlayWindow                 # backend-provided
  ├── content: PopupContent                 # toolkit-specific widget tree
  ├── try_*()                               # unchanged business logic
  └── try_move(), try_timeout() use window.move / window.set_opacity
```

`PopupContent` has a Tk impl (current code) and a GTK impl (Phase 2). Subclasses `ImagePopup`/`VideoPopup`/`SubliminalPopup` keep their decision logic and just hand the right content widget to the backend.

### 4.3 Monitor enumeration

`utils.primary_monitor()` / `random_monitor()` go through `backend.list_monitors()`. On `NiriBackend`, that's `Gdk.Display.get_default().get_monitors()` returning `GdkMonitor`s. On `TkBackend`, it's the current `screeninfo` call.

Settings field `disabled_monitors` keys by `name` — verify GdkMonitor connector names match screeninfo names. They usually do on Wayland (`DP-1`, `HDMI-A-1`).

### 4.4 mpv embedding on Wayland

Current code (`features/video_player.py:46-55`) forces GPU context to `x11`/`x11egl`/`x11vk` and embeds via Tk `winfo_id()` (X11 XID).

Wayland path:
- Set `gpu-context=wayland`, `vo=libmpv`, use **`mpv-render` API** (already exposed by `python-mpv` as `MPV.create_render_context(api_type='opengl')`).
- Host widget is a `Gtk.GLArea`. On `render` signal, mpv renders into the GL FBO.
- Reference impls exist (e.g. `gnome-mpv`, `Celluloid`); we follow that pattern.
- Subprocess mpv mode (`settings.mpv_subprocess`) currently passes `winfo_id()` to a child process. On Wayland we cannot pass an XID. Subprocess mode is **disabled on the niri backend** for v1 (log a warning, force in-process). Phase 5 may add a Wayland-native subprocess mode using pipes for render commands.

### 4.5 Process model

Engine and config are **separate processes** today ([`paths.Process.MAIN`](file:///home/ondine/.local/share/edgeware/src/paths.py)). Stays that way. Each picks its backend independently. Config can use the GTK backend even when the engine doesn't (e.g., user wants the prettier config window but disabled the niri runtime path).

---

## 5. niri integration (D5)

### 5.1 Files shipped

- `assets/niri/edgeware.kdl` — niri configuration snippet (see §5.2).
- Installer/`setup.sh` (or first-launch on the engine) **does NOT** auto-edit `~/.config/niri/config.kdl`. Instead, it prints a message and writes `~/.config/niri/edgeware.kdl`, telling the user to add one `include` line to their config:

  ```
  include "edgeware.kdl"
  ```

- Optional `make_desktop_icons` adds a "Install niri integration" `.desktop` entry that copies the snippet (idempotent).

### 5.2 `edgeware.kdl` contents (draft)

```kdl
// Edgeware++ niri integration — auto-generated, edit at your own risk

// Global panic hotkey (configurable: this is the default — Mod+Shift+Escape)
binds {
    Mod+Shift+Escape { spawn "bash" "-c" "~/.local/share/edgeware/panic.sh"; }
}

// Layer rules for Edgeware overlay surfaces.
// All Edgeware popups use namespaces prefixed with "edgeware-".
layer-rule {
    match namespace="^edgeware-popup$"
    place-within-backdrop false
    // Popups draw above other windows but below the screen-lock/notifications
}

layer-rule {
    match namespace="^edgeware-splash$"
    place-within-backdrop false
}

layer-rule {
    match namespace="^edgeware-subliminal$"
    place-within-backdrop false
}

// Optional: window rule for the Tk config window when it's running under XWayland
window-rule {
    match app-id="Edgeware++"
    open-floating true
}
```

### 5.3 Panic hotkey contract

- Engine reads `settings.global_panic_key` (already exists).
- On first launch under niri (or via a "Regenerate niri snippet" button in the config), we **rewrite** `edgeware.kdl` to use the user's chosen keybind.
- The keybind unconditionally `spawn`s `panic.sh`, which calls `panic.py` as a script — already supported by the [`if __name__ == "__main__": send_panic()`](file:///home/ondine/.local/share/edgeware/src/panic.py#L103-L104) path. The running engine receives the IPC panic message and shuts down. **No code changes to `panic.py` needed.**
- This bypasses the broken `pynput` global-listener path on Wayland, which on Wayland only sees keys when an XWayland-owned window has focus.
- The pynput listener stays as-is for X11 users. On niri it gets disabled (no-op'd) to save the process.

### 5.4 Wallpaper

Already works via `qs -c noctalia-shell ipc call wallpaper set`. No changes.

---

## 6. Dependencies

### 6.1 Python (`requirements.txt` additions, Linux-only conditional)

```
PyGObject; platform_system == 'Linux'
pycairo; platform_system == 'Linux'
```

`gtk4-layer-shell` Python bindings are auto-discovered via PyGObject introspection — no separate Python package. We `require_version("Gtk", "4.0")` + `require_version("Gtk4LayerShell", "1.0")`.

### 6.2 System packages (documented in setup.sh)

Distro-specific, but the canonical names are:
- `gtk4` (and dev if installing from source) — runtime, always already installed on niri/GNOME-adjacent setups
- `gtk4-layer-shell` (Arch: `gtk4-layer-shell`, Fedora: `gtk4-layer-shell`, Debian: `libgtk4-layer-shell-dev` + runtime)
- `python-gobject` / `python3-gi` / `PyGObject`
- `gobject-introspection` typelibs for Gtk-4.0 and Gtk4LayerShell-1.0

`setup.sh` is updated to detect Wayland + niri and run a friendly preflight check that prints the missing packages per-distro. Missing packages → user gets a clear message; engine falls back to TkBackend.

### 6.3 Dependency we are removing on the Wayland path

- `python-xlib` becomes optional on niri. Stays installed because `screeninfo` imports it on Linux, but on the niri code path we don't call it. Removing it from `requirements.txt` would break X11 users — **keep it**.

---

## 7. Phased delivery

Each phase is a separately reviewable PR. Phases 0-3 are the engine port. Phases 4-7 are the config port. Phase 8 is cleanup.

### Phase 0 — Foundation (no behavior change)

**Deliverables**
- `src/os_utils/display_server.py`: `is_wayland()`, `wayland_compositor()`, `is_niri()`. Replaces the duplicated `is_wayland` in `features/misc.py` (and fixes the redundant check on line 85).
- `src/os_utils/backend.py`: protocol/abstract classes.
- `src/os_utils/backend_tk.py`: wraps existing Tk window code, no functional change. All current `set_borderless`/`set_clickthrough` paths route through it.
- `make_backend()` factory chooses Tk (always, for now — Niri backend not yet implemented).
- Plumb backend through `Popup.__init__`, `StartupSplash.__init__`, `Prompt.__init__`, `SubliminalPopup.__init__`. They still call Tk under the hood; the abstraction is the only change.
- `utils.list_monitors()` wrapper around `backend.list_monitors()`. Tk backend implementation = current `screeninfo` call.

**Verification**
- `./edgeware.sh` runs end-to-end on the current X11 (and niri/XWayland) setup, identical behavior.
- All popup types appear, video plays, fade-out works, panic works.
- `python -m compileall src` clean.

### Phase 1 — niri panic hotkey + niri detection

**Deliverables**
- `NiriBackend` skeleton (`backend_niri.py`) that imports GTK + layer-shell at module top, raises `ImportError` cleanly if missing.
- `make_backend()` returns `NiriBackend` when `is_niri()` and the GTK imports succeed.
- For Phase 1 the `NiriBackend` **delegates all overlay/popup methods to TkBackend** — only `list_monitors()` is real (uses GdkMonitor).
- `assets/niri/edgeware.kdl` template.
- `os_utils/niri_integration.py`: `install_niri_snippet()` writes `~/.config/niri/edgeware.kdl` with the user's panic key. Called from a new config tab button "Install niri integration".
- Engine on niri: disables `pynput` global listener, logs that panic is handled by niri keybind.
- A "panic" CLI invocation (`python -m panic` or `panic.sh`) is already there — verify it dispatches IPC correctly.

**Verification**
- Fresh niri session, snippet installed, `Mod+Shift+Escape` triggers panic from any focused window (including non-Edgeware).
- Test the snippet does not break niri config validation (`niri validate`).
- GdkMonitor names match user's `~/.config/niri/config.kdl` output names.

### Phase 2 — Wayland-native popups (image + subliminal + splash + prompt)

**Deliverables**
- `NiriBackend.make_overlay()` returns a real GTK4 layer-shell window:
  - `Gtk4LayerShell.init_for_window(window)`
  - layer = `OVERLAY`
  - keyboard mode = `EXCLUSIVE` for `Prompt`, `NONE` otherwise
  - anchor = none (free placement via `Gtk4LayerShell.set_margin()` from a chosen `GdkMonitor`)
  - namespace = `edgeware-popup` / `edgeware-splash` / `edgeware-subliminal`
- `OverlayWindow` GTK impl:
  - `set_clickthrough` → `surface.set_input_region(Cairo.Region())` (empty)
  - `set_opacity` → `Gtk.Widget.set_opacity()` (animatable for fade-out)
  - `move(x, y)` → adjust layer-shell margins relative to the anchored monitor
  - `on_close` / `on_key` / `on_click` → wire `Gtk` signal handlers, translate keysyms to Tk-compatible names (so `settings.panic_key` keeps working)
- `PopupContent` GTK impl: `Gtk.Overlay` with `Gtk.Picture` (PIL → `Gdk.Texture` via `Gdk.Texture.new_from_bytes`) + close button + label widgets matching Tk theme via CSS.
- Splash content: text + image.
- Subliminal content: just the text label.
- Prompt content: scrolling text + entry box (already simple).
- Engine main loop integration: spawn a GLib main loop in a dedicated thread, hand work to it via `GLib.idle_add`. Tk root loop remains primary. **`root.after(...)` callbacks that touch GTK widgets must marshal to the GLib thread.** A helper `gtk_call(fn)` does this. Audit current `after()` call sites and update.

**Verification** (executed in this order; failure of any item blocks merge)

| # | Action | Command / Tool | Expected result |
|---|---|---|---|
| V2.1 | Run engine on niri with image-only pack, `image_chance=100`, all other roll chances 0, `delay=1000`. | `XDG_CURRENT_DESKTOP=niri ./edgeware.sh` | Within 5s: an image popup appears. `niri msg windows` (or `niri msg layers`) shows a layer surface in namespace `edgeware-popup` on the focused output. Tk root window is hidden (no XWayland client visible). |
| V2.2 | Set `clickthrough_enabled=true` in config, restart engine. With a popup visible, click through the popup onto a window behind it. | manual mouse click | The click is delivered to the window behind, not the popup. The popup stays visible. |
| V2.3 | Set `timeout_enabled=true`, `timeout=2000`. Trigger an image popup. | wall-clock + visual | Popup fades out smoothly from current opacity to 0 over ~1.5s, then disappears. No flicker, no abrupt close. |
| V2.4 | Set `moving_chance=100`, `moving_speed=5`. Trigger an image popup. | visual + `niri msg layers` repeated calls | Popup translates across the screen, bounces off all four edges of its monitor. Coordinates stay within the monitor bounds reported by `niri msg outputs`. |
| V2.5 | Set 3 monitors in niri, disable none, run with `image_chance=100`, `delay=200` for 30s. | count popups per output via tally | At least 1 popup appears on each of the 3 outputs. Distribution roughly uniform (chi-square or just inspection). |
| V2.6 | Add the focused output to `disabled_monitors` (by Wayland connector name from `niri msg outputs`), restart. Run for 30s. | tally per output | Zero popups appear on the disabled output. |
| V2.7 | Subliminal-only run: `subliminal_chance=100`, others 0. | `XDG_CURRENT_DESKTOP=niri ./edgeware.sh` | Centered text on a random output, namespace `edgeware-subliminal`, fades after `subliminal_timeout`. |
| V2.8 | Splash enabled: `startup_splash=1`. | restart engine | Splash appears centered on primary output during init, disappears once `start_main()` runs. No Tk window flashes. |
| V2.9 | Prompt-only run: `prompt_chance=100`, others 0. | trigger one | Prompt window appears centered, accepts keyboard input, `panic_key` press triggers panic + clean shutdown. |
| V2.10 | Press `settings.panic_key` while any popup is focused. | keyboard | All popups close, wallpaper reset, engine exits cleanly (exit 0, no Python traceback in logs). |
| V2.11 | X11 regression: run on a real X11 session (`startx` or VM). | `XDG_SESSION_TYPE=x11 ./edgeware.sh` | All popups still render via Tk path. `make_backend()` returns `TkBackend`. Behavior identical to current main branch. |
| V2.12 | Code health. | `python -m compileall src && python -c "import ast; [ast.parse(open(f).read()) for f in __import__('glob').glob('src/**/*.py', recursive=True)]"` | Exit 0. |
| V2.13 | No regressions in existing tests if any. | `pytest` (if test suite exists) | All previously-passing tests still pass. (Note: no test suite found at planning time — confirm before Phase 2 starts.) |

### Phase 3 — Wayland-native video popups

**Deliverables**
- `VideoPlayerGtk`: `Gtk.GLArea` host, mpv via `mpv-render` API with `wayland` GPU context. Replaces `Tk.Label`-based `VideoPlayer` on the niri backend only.
- `gpu-context` selection logic in [`video_player.py:46-55`](file:///home/ondine/.local/share/edgeware/src/features/video_player.py#L46-L55) becomes: niri backend → `wayland`; Tk backend → existing `x11`/`x11egl`/`x11vk` fallback chain.
- Overlay image (hypno mode) still works via `mpv.create_image_overlay()` API.
- Subprocess mode (`settings.mpv_subprocess`) → log warning + force in-process on niri.

**Verification**

| # | Action | Command / Tool | Expected result |
|---|---|---|---|
| V3.1 | Video-only run on niri, `video_chance=100`, `video_hardware_acceleration=1`, `max_video=1`. | `XDG_CURRENT_DESKTOP=niri ./edgeware.sh` | Video popup appears, plays, loops. `mpv --msg-level=all=v` (via env `MPV_VERBOSE=1` if added, or check Edgeware logs) shows `gpu-context=wayland` selected. No `Xlib` / `X11` strings in mpv init log. |
| V3.2 | Hardware-decode probe. | `vainfo` (or `vdpauinfo`) before; check `nvidia-smi` / `radeontop` / `intel_gpu_top` during playback | GPU video engine shows non-zero utilization. CPU video-decode threads idle. |
| V3.3 | Disable hardware decode in settings, restart, replay video. | settings + restart | Video still plays. CPU video-decode active. |
| V3.4 | Hypno mode (image popup with `hypno_chance=100`, animated hypno overlay). | trigger image popup | mpv plays the hypno video underneath, PIL image draws as overlay on top via `create_image_overlay`. Output looks identical to current XWayland behavior (side-by-side screenshots in PR). |
| V3.5 | Denial filter (shader). | `denial_chance=100` + video popup | Either gaussian-blur or pixelize shader applies to the playing video. Verify by visual diff against unfiltered playback. |
| V3.6 | Concurrent videos: `max_video=3`, `video_chance=100`, `delay=500`. | run for 30s | 3 simultaneous video popups, each playing different files, no crashes, no audio mixer chaos beyond what already exists on X11. |
| V3.7 | `mpv_subprocess=1` on niri. | restart engine, trigger video | Log shows warning "subprocess mpv mode unsupported on niri backend, falling back to in-process". Video still plays in-process. |
| V3.8 | mpv Wayland context failure simulation: set env `LIBGL_ALWAYS_SOFTWARE=1` or break GPU access. | restart, trigger video | Fallback chain executes: tries `wayland`, then `wayland-vk`, then `sw`. Logs each attempt. Eventually plays via software, or logs clear "no GPU context available". No silent hang. |
| V3.9 | Performance comparison. | `perf stat -e cycles,instructions ./edgeware.sh` for 60s with `video_chance=100` on niri (Wayland backend) vs niri (forced Tk backend via env var `EDGEWARE_FORCE_TK=1`) | Wayland backend cycles ≤ Tk-on-XWayland backend cycles. (Soft target; mostly a sanity check that we didn't regress.) |
| V3.10 | X11 regression. | `XDG_SESSION_TYPE=x11 ./edgeware.sh` with video_chance=100 | Existing `x11`/`x11egl`/`x11vk` selection logic unchanged. Video plays via Tk path. |
| V3.11 | Code health. | `python -m compileall src` | Exit 0. |

### Phase 4 — Config window GTK4 port (no layer-shell)

This is the big one. ~2,900 lines of Tk widgets to translate. Strategy:

**4a. Skeleton** — `src/config/gtk_window/__init__.py` mirrors `config/window/__init__.py`. Provides `ConfigWindowGtk` with `Gtk.Notebook` (tabs), `Gtk.HeaderBar`, save/load wiring to existing `Vars`.
**4b. Widget translation table** — drop-in helpers in `config/gtk_window/widgets/`: `BoolToggle` (`Gtk.Switch`), `IntSlider` (`Gtk.Scale`), `StringEntry`, `FileChooser`, `ScrollFrame` (`Gtk.ScrolledWindow`), `ListEdit`, theme dropdown.
**4c. Variable bridge** — `Vars` uses Tk `BooleanVar`/`StringVar`/`IntVar`. New `GtkVars` wrapper exposes the same `.get()`/`.set()`/`.entries` API backed by Python primitives + `GObject.Property` for change-notify. Saves to the same JSON via existing `write_save`.
**4d. Tabs, one per PR-able commit:** start (general), info (general), default_file (general), modes, corruption, popup_tweaks, popup_types, moods, wallpaper, booru, dangerous_settings, troubleshooting, tutorial. 13 tabs. Group commits by tab.
**4e. Key listeners** — re-implement `KeyListenerWindow` and `request_global_panic_key` in GTK. On niri, the global-panic-key UI changes: instead of asking pynput to listen, we just write the keybind into `edgeware.kdl` and ask the user to reload niri.
**4f. `main_config.py`** picks GTK config if `is_linux()` (regardless of compositor — GTK4 works fine under X11/XWayland too). Tk config kept under a `--legacy-tk` flag for one release as escape hatch.

**Verification**

For each per-tab commit (4d), the relevant subset of V4.1–V4.4 runs on that tab only. The full table below runs before merging the Phase 4 umbrella PR.

| # | Action | Command / Tool | Expected result |
|---|---|---|---|
| V4.1 | Settings round-trip. Capture current `~/.local/share/edgeware/data/config.json`; open GTK config; click "Save" without changes; diff. | `cp data/config.json /tmp/before.json && ./config.sh` → save → `diff /tmp/before.json data/config.json` | Diff is empty OR contains only formatting/key-order changes. Every setting key from `default_config.json` round-trips byte-identically for booleans, ints, floats, strings, lists. |
| V4.2 | Toggle every boolean in the GTK UI, save, restart engine, observe the matching runtime behavior is enabled/disabled correctly. | manual checklist (one row per boolean in `config/items.py`) | Each toggle has the expected runtime effect (or no effect for inert settings). No setting is unreachable from the GTK UI. |
| V4.3 | Theme switching: switch through every theme (Original / Dark / The One / Ransom / Goth / Bimbo). | dropdown + restart config | GTK CSS reflects each theme. Color values match Tk theme colors documented in `config/window/utils.py:set_widget_states_with_colors`. Screenshot comparison saved in PR. |
| V4.4 | Pack import flow. Prep: create a minimal valid pack zip at `/tmp/edgeware-test-pack.zip` (an `info.json` + one image under `media/`); this fixture is committed under `tests/fixtures/test-pack.zip` as part of Phase 4. In the GTK config, open the pack tab, choose "Import new pack", select the zip, name it `test-pack`. | manual import flow + post-checks below | After import: (a) directory `~/.local/share/edgeware/data/packs/test-pack/` exists with the unpacked contents; (b) clicking "Use this pack" updates `data/config.json` so `"packPath": "test-pack"`; (c) restart engine — `pack.info.name` in logs matches the imported pack; (d) the alternate "change default pack" flow instead overwrites `~/.local/share/edgeware/resource/` and leaves `packPath` as `null`/`"default"`. |
| V4.5 | Dangerous-settings warning. | toggle a known-dangerous setting (e.g. `corruption_mode` + a major-level danger key) → save → quit | `safe_check` dialog appears via GTK with the same warning content as Tk. Cancel returns to editor; confirm saves. |
| V4.6 | Key-listener flow (panic key assignment) on niri. | click "Set Global Panic Key" → press Ctrl+Alt+Shift+Q | UI displays the captured key. `settings.global_panic_key` stored. `edgeware.kdl` updated (or banner appears prompting user to regen + reload niri). |
| V4.7 | Key-listener flow on X11. | same as V4.6 on `XDG_SESSION_TYPE=x11` | pynput-based listener still works. Key captured. Stored. |
| V4.8 | Side-by-side visual QA. | open both Tk config and GTK config | Every tab visible in Tk is visible in GTK with the same widget set. Screenshots in PR. Functional parity, not pixel parity. |
| V4.9 | `--legacy-tk` escape hatch. | `./config.sh --legacy-tk` | Tk config opens. Edits round-trip. Confirms the fallback is alive. |
| V4.10 | Code health. | `python -m compileall src` | Exit 0. |
| V4.11 | First-launch flow. | delete `data/config.json` → `./config.sh` | First-launch wizard runs in GTK, produces a valid config. Engine starts cleanly. |

### Phase 5 — Cleanup

**Deliverables**
- Remove `os_utils/linux.py`'s niri-specific Tk branches (`set_borderless` no longer used on niri).
- Remove dead `wait_visibility` / `winfo_id` paths on the niri backend.
- Document compositor-support matrix in README:
  - niri → native Wayland (GTK4 + layer-shell)
  - sway / hyprland / kwin / mutter → XWayland (Tk)
  - X11 → Tk
  - Windows / macOS → unchanged
- Update `setup.sh` to install GTK4 deps with per-distro hints.
- Remove the redundant Wayland-detection clause on [`misc.py:85`](file:///home/ondine/.local/share/edgeware/src/features/misc.py#L85) (already done in Phase 0 but verify).
- Optional: drop `--legacy-tk` config escape hatch added in Phase 4 (only if Phase 4 has been in users' hands for one release cycle without bug reports).

**Verification**

| # | Action | Command / Tool | Expected result |
|---|---|---|---|
| V5.1 | Dead-code grep. | `grep -rn "set_borderless\|wait_visibility\|winfo_id" src/os_utils/ src/features/ | grep -v backend_tk` | Zero matches in non-Tk-backend files. (Tk backend may legitimately retain them.) |
| V5.2 | Duplicate `is_wayland` removed. | `grep -rn "def is_wayland" src/` | Exactly one definition, in `os_utils/display_server.py`. |
| V5.3 | niri end-to-end smoke. | `XDG_CURRENT_DESKTOP=niri ./edgeware.sh` with a representative pack, run for 60s | Image, video, subliminal, prompt popups all appear. Panic via niri keybind shuts down cleanly. |
| V5.4 | X11 regression smoke. | `XDG_SESSION_TYPE=x11 ./edgeware.sh` same scenario | Identical behavior to pre-port main branch. |
| V5.5 | sway regression smoke (XWayland fallback). | `XDG_CURRENT_DESKTOP=sway ./edgeware.sh` (or any non-niri Wayland) | `make_backend()` returns `TkBackend`. Popups render via XWayland. No GTK code paths exercised. Log line confirms this. |
| V5.6 | README compositor matrix present. | `grep -E "niri.*native\|sway.*XWayland" README.md` | At least one match for each compositor row. |
| V5.7 | `setup.sh` per-distro hints. | inspect `setup.sh` | Branches for Arch, Fedora, Debian/Ubuntu printing the correct GTK4 + layer-shell package names. Test on at least one distro (Arch, since that's the dev's). |
| V5.8 | Compile validation. | `python -m compileall src` | Exit 0. |
| V5.9 | Static analysis. | `python -c "import ast,glob; [ast.parse(open(f).read()) for f in glob.glob('src/**/*.py', recursive=True)]"` | Exit 0. |
| V5.10 | Fresh-install dry run on a clean VM (or container). | follow README install instructions verbatim | Engine starts, popups appear, panic works. No manual fixups required beyond what README documents. |

### Phase 6 — Stretch (post-v1)

- **Wayland panic listener via GlobalShortcuts portal** — so users don't have to install the niri snippet manually. Defer; portal support varies.
- **Compositor support beyond niri** — sway/hyprland trivially work with the same GTK4+layer-shell code; just enable when `wayland_compositor() in {sway, hyprland}`. Gate behind testing.
- **Drop Tk root loop entirely** — replace `root.after()` with `GLib.timeout_add`. Smaller resident footprint, but invasive.

---

## 8. Cross-cutting risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| GTK4 GLib main loop ↔ Tk main loop deadlock or starvation | Medium | High | Run GLib loop in a dedicated thread; `gtk_call()` helper for cross-thread marshaling; **never** touch Tk widgets from GLib thread or vice versa. |
| `gtk4-layer-shell` not packaged on user's distro | Medium | Medium | Detect missing typelib at import; fall back to TkBackend with a warning. Document distro packages. |
| mpv `wayland` GPU context fails on user's GPU | Low | High | Try `wayland` first, fall back to `wayland-vk`, then disable hwdec and use `sw`. Same fallback chain pattern as the current X11 list. |
| GdkMonitor names differ from `screeninfo` names → `disabled_monitors` setting silently breaks | Medium | Medium | Phase 0 logs both names side by side on startup; users can fix their settings; we add a migration that prefers connector names. |
| Tk root window mainloop kept just for `.after()` — wasted process resources | Low | Low | Acceptable for v1; revisit in Phase 6. |
| `pynput` listener spawn cost on niri (we disable it) breaks something downstream | Low | Medium | Audit every reader of the listener; the queue receive thread becomes a no-op; verify panic key in config UI uses GTK key event, not pynput. |
| Click-through via empty input region on niri behaves differently than X11 shape | Medium | Low | Test with `moving` popups, layered popups, and clickthrough toggled at runtime. Expected to be cleaner on Wayland actually. |
| Fade-out animation timing under GLib differs from Tk `.after()` | Low | Low | Use `GLib.timeout_add` directly in the GTK content; preserve current 15ms cadence. |
| User edits `edgeware.kdl` themselves and we overwrite it | Medium | Medium | Detect existing file, diff, prompt user before overwriting; or write to `edgeware.kdl.new` and tell user. |
| Niri's layer-shell behavior changes between versions | Medium | Low | Pin minimum tested niri version in README; CI smoke test on the dev's niri. |

---

## 9. Out of scope but worth noting

- **Wayland portal-based screenshot/screencast hooks** (not used by Edgeware today).
- **Fractional scaling** — GTK4 handles it; double-check `compute_geometry` math uses logical pixels consistently.
- **HiDPI cursor handling** for clickthrough.
- **A11y** — GTK4 a11y is significantly better than Tk; opportunity but not a goal.

---

## 10. Approval checklist (before any code)

- [ ] User reviews this plan
- [ ] Momus review (clarity/verifiability/completeness)
- [ ] Plan revised based on Momus output
- [ ] User gives explicit "go" on implementation
- [ ] Phase 0 PR drafted

---

## 11. Phase 0 file-by-file change list (preview, not yet authorized)

When Phase 0 is approved we will touch:
- **new** `src/os_utils/display_server.py`
- **new** `src/os_utils/backend.py`
- **new** `src/os_utils/backend_tk.py`
- **edit** `src/os_utils/__init__.py` (export `make_backend`, `list_monitors`)
- **edit** `src/os_utils/linux.py` (route through backend)
- **edit** `src/features/misc.py` (remove duplicated `is_wayland`)
- **edit** `src/features/popup.py` (`Popup.__init__` accepts backend)
- **edit** `src/features/startup_splash.py`, `prompt.py`, `subliminal_popup.py` (same)
- **edit** `src/utils.py` (`primary_monitor`/`random_monitor` go through backend)
- **edit** `src/main_edgeware.py`, `src/main_config.py` (construct backend, pass it down)

No new dependencies in Phase 0. No new runtime requirements. Pure refactor.
