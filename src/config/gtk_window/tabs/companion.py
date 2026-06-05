# Copyright (C) 2025 Araten & Marigold
#
# This file is part of Edgeware++.
#
# Edgeware++ is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Edgeware++ is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Edgeware++.  If not, see <https://www.gnu.org/licenses/>.

import os
import re
import threading
from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from config.gtk_window.widgets import AdwComboRow, AdwEntryRow, AdwSliderRow, AdwSwitchRow
from config.vars import Vars
from features.companion import llm

COMPANION_TEXT = (
    "An optional AI companion that reacts to you on screen. Bring your own "
    "inference: a local Ollama server keeps everything on your machine, any "
    "OpenAI-compatible endpoint works too, or the scripted mode needs no AI at "
    "all. Choose a model and use Test to check it responds."
)
BACKENDS = {
    "ollama": "Ollama (local)",
    "openai": "OpenAI-compatible",
    "opencode": "opencode server",
    "opencode-cli": "opencode (run CLI)",
    "scripted": "Scripted (no AI)",
}
CONTROL_MODES = {
    "tags": "Command tags (any model)",
    "tools": "Tool calling (needs a tool-capable model)",
}
CONTROL_TEXT = (
    "Let the companion act in Edgeware: spawn popups and prompts, send "
    "notifications, change the wallpaper and pulse the toy. Only safe, "
    "rate-limited actions are exposed and Panic always works. Tags work with "
    "any model; tool calling needs a model that supports it."
)
PRIVACY_TEXT = (
    "Window awareness feeds the name of the app you are focused on to the "
    "companion. With a cloud backend, that — and the companion's prompts — "
    "leave your machine. Keep it on a local backend to stay private."
)
SCREENSHOT_TEXT = (
    "Screen awareness sends a screenshot to the backend for richer reactions "
    "(needs a vision model). On niri it captures just the focused window (via "
    "the clipboard, which is then restored); otherwise the whole screen. Very "
    "sensitive — only use a trusted LOCAL backend. Overrides window awareness."
)
CLIPBOARD_TEXT = (
    "Clipboard awareness lets the companion react to images you copy (needs a "
    "vision model). Every copied image is sent to the backend — including "
    "private screenshots — so only use a trusted LOCAL backend."
)

# niri blurs layer-shell surfaces behind anything translucent. That looks good
# behind popups but wrong behind the companion's rounded bubble. Guide niri
# users to a layer-rule that blurs the popups but excludes the companion + HUD.
_NIRI_BLUR_SNIPPET = (
    '// Add to ~/.config/niri/layer-rules.kdl:\n'
    'layer-rule {\n'
    '    match namespace="^edgeware-.*$"\n'
    '    exclude namespace="^edgeware-companion$"\n'
    '    exclude namespace="^edgeware-hud$"\n'
    '    background-effect {\n'
    '        blur true\n'
    '        xray false\n'
    '    }\n'
    '}'
)
_NIRI_LAYER_RULES = Path.home() / ".config" / "niri" / "layer-rules.kdl"


def _is_niri() -> bool:
    return bool(os.environ.get("NIRI_SOCKET"))


def _niri_blur_configured() -> bool:
    if not _NIRI_LAYER_RULES.is_file():
        return False
    content = _NIRI_LAYER_RULES.read_text(encoding="utf-8", errors="replace")
    return 'namespace="^edgeware' in content


def _niri_append_config(path: "Path", snippet: str) -> "str | None":
    lines = snippet.splitlines()
    body = "\n".join(lines[1:] if lines and lines[0].startswith("//") else lines)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        sep = "\n\n" if path.is_file() and path.stat().st_size > 0 else ""
        with path.open("a", encoding="utf-8") as f:
            f.write(sep + body + "\n")
        return None
    except OSError as e:
        return str(e)


class CompanionTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars) -> None:
        super().__init__()
        self._vars = vars

        # Default the per-slot backends to the main backend so their combos show
        # a concrete choice (empty = "follow main" is still honoured at runtime).
        for slot in (vars.companion_vision_backend, vars.companion_memory_backend):
            if not (slot.get() or "").strip():
                slot.set(vars.companion_backend.get())

        group = Adw.PreferencesGroup(title="AI Companion", description=COMPANION_TEXT)
        self.add(group)
        group.add(AdwSwitchRow("Enable Companion", vars.companion_enabled))

        # Connection settings per backend type (one connection per type).
        conn = Adw.PreferencesGroup(
            title="Backend Connections",
            description="Set the connection for each backend type you use. Each model "
                        "below picks which of these backends to run on.")
        self.add(conn)
        conn.add(AdwEntryRow("Ollama URL", vars.ollama_url))
        conn.add(AdwEntryRow("OpenAI-compatible URL", vars.openai_url))
        conn.add(AdwEntryRow("OpenAI key", vars.openai_key, password=True))
        conn.add(AdwEntryRow("opencode URL (optional)", vars.opencode_url))
        conn.add(AdwEntryRow("opencode key (optional)", vars.opencode_key, password=True))

        # Models — backend + detected-model dropdowns, no free text.
        models = Adw.PreferencesGroup(title="Models")
        self.add(models)
        models.add(AdwComboRow("Chat backend", vars.companion_backend, BACKENDS))
        models.add(self._model_picker(vars, vars.companion_model, vars.companion_backend,
                                      subtitle="Main chat / text model"))
        models.add(AdwComboRow("Vision backend", vars.companion_vision_backend, BACKENDS))
        models.add(self._model_picker(vars, vars.companion_vision_model, vars.companion_vision_backend,
                                      subtitle="Screenshot / image analysis; falls back to the chat model"))

        # niri-only: stop the compositor blurring behind the companion bubble.
        if _is_niri():
            niri_group = Adw.PreferencesGroup(
                title="niri Display",
                description="niri blurs behind translucent layer-shell surfaces. That suits popups but looks wrong behind the companion bubble.")
            self.add(niri_group)
            niri_group.add(self._niri_blur_row())

        persona = Adw.PreferencesGroup(
            title="Persona",
            description="Override the pack's companion. Leave blank to use the pack's companion.json (or the built-in default).")
        self.add(persona)
        persona.add(AdwEntryRow("Name", vars.companion_name))
        persona.add(self._avatar_row(vars))
        persona.add(self._text_editor("System prompt", vars.companion_system_prompt))
        persona.add(self._text_editor("Memory / about the user", vars.companion_memory))

        # ---- Auto-memory (facts the companion learns) --------------------
        mem_group = Adw.PreferencesGroup(
            title="Learned Memory",
            description="When on, the companion summarises each session into durable facts about you (kept locally, editable below). Uses the optional model below, else the main model.")
        self.add(mem_group)
        mem_group.add(AdwSwitchRow("Auto-memory", vars.companion_auto_memory))
        mem_group.add(AdwComboRow("Memory backend", vars.companion_memory_backend, BACKENDS))
        mem_group.add(self._model_picker(vars, vars.companion_memory_model, vars.companion_memory_backend,
                                         subtitle="Memory-extraction model; falls back to the chat model"))
        mem_group.add(self._memory_facts_editor())

        behaviour = Adw.PreferencesGroup(title="Behaviour")
        self.add(behaviour)
        behaviour.add(AdwSliderRow("Idle Chatter Chance", vars.companion_chatter_chance, 0, 100))
        behaviour.add(AdwSliderRow("Reaction Chance", vars.companion_react_chance, 0, 100,
                                   subtitle="How often the companion reacts to popups and denials."))
        behaviour.add(AdwSliderRow("Observe Interval", vars.companion_observe_interval, 0, 300,
                                   subtitle="Time between timed check-ins (0 = react to focus changes instead).",
                                   unit="s"))
        behaviour.add(AdwSwitchRow(
            "Follow Around", vars.companion_follow,
            subtitle="Roam the screen and move to whichever monitor you're using, instead of sitting in a corner."))
        behaviour.add(AdwSwitchRow("Greet on Start", vars.companion_greet_on_start))
        behaviour.add(AdwSwitchRow(
            "Window Awareness", vars.companion_window_awareness, subtitle=PRIVACY_TEXT))
        behaviour.add(AdwSwitchRow(
            "Screen Awareness", vars.companion_screenshot_awareness, subtitle=SCREENSHOT_TEXT))
        behaviour.add(AdwSwitchRow(
            "Clipboard Awareness", vars.companion_clipboard_awareness, subtitle=CLIPBOARD_TEXT))

        control = Adw.PreferencesGroup(title="Control", description=CONTROL_TEXT)
        self.add(control)
        control.add(AdwSwitchRow("Let Companion Control Edgeware", vars.companion_control))
        control.add(AdwComboRow("Control Method", vars.companion_control_mode, CONTROL_MODES))

        # ---- Test --------------------------------------------------------
        test_group = Adw.PreferencesGroup(
            title="Test", description="Ask the configured backend to say hello.")
        self.add(test_group)
        self._test_btn = Gtk.Button(label="Test")
        self._test_btn.add_css_class("suggested-action")
        self._test_btn.connect("clicked", self._on_test)
        self._spinner = Adw.Spinner()
        self._spinner.set_visible(False)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(self._spinner)
        head.append(self._test_btn)
        test_group.set_header_suffix(head)

        self._reply = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self._reply.add_css_class("dim-label")
        self._reply.set_margin_top(4)
        self._reply.set_margin_bottom(4)
        test_group.add(self._reply)

    def _text_editor(self, label_text, variable) -> Gtk.Widget:
        """A multiline editor bound to a ConfigVar."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        label = Gtk.Label(label=label_text, xalign=0)
        label.add_css_class("dim-label")
        box.append(label)

        view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False)
        view.set_top_margin(6)
        view.set_bottom_margin(6)
        view.set_left_margin(6)
        view.set_right_margin(6)
        buf = view.get_buffer()
        buf.set_text(str(variable.get() or ""))

        def on_changed(b) -> None:
            variable.set(b.get_text(b.get_start_iter(), b.get_end_iter(), False))
        buf.connect("changed", on_changed)

        # Reflect external changes (preset / pack apply) without looping.
        def on_var(value) -> None:
            text = str(value or "")
            if buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False) != text:
                buf.set_text(text)
        variable.trace_add(on_var)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(120)
        scroller.set_child(view)
        frame = Gtk.Frame()
        frame.add_css_class("card")
        frame.set_child(scroller)
        box.append(frame)
        return box

    def _niri_blur_row(self) -> Gtk.Widget:
        """A copy-pastable niri layer-rule that keeps blur on the popups but
        excludes the companion bubble and HUD. niri reloads it automatically."""
        already = _niri_blur_configured()

        row = Adw.ActionRow()
        row.set_activatable(False)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_margin_start(12)
        vbox.set_margin_end(12)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)

        # Status stack: info (not configured) vs verified (configured)
        info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        info_icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
        info_icon.set_valign(Gtk.Align.START)
        info_lbl = Gtk.Label(wrap=True, xalign=0, hexpand=True)
        info_lbl.set_text(
            "Seeing a blur behind the companion? Add this layer-rule. It keeps "
            "the frosted blur on popups but excludes the companion and the "
            "gamification HUD so they render crisp:")
        info_box.append(info_icon)
        info_box.append(info_lbl)

        ok_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ok_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
        ok_icon.add_css_class("success")
        ok_icon.set_valign(Gtk.Align.CENTER)
        ok_lbl = Gtk.Label(wrap=True, xalign=0, hexpand=True)
        ok_lbl.set_text("layer-rules.kdl is configured — companion and HUD will render without blur.")
        ok_box.append(ok_icon)
        ok_box.append(ok_lbl)

        status_stack = Gtk.Stack()
        status_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        status_stack.add_named(info_box, "info")
        status_stack.add_named(ok_box, "ok")
        status_stack.set_visible_child_name("ok" if already else "info")
        vbox.append(status_stack)

        code_view = Gtk.TextView()
        code_view.set_editable(False)
        code_view.set_monospace(True)
        code_view.set_wrap_mode(Gtk.WrapMode.NONE)
        code_view.set_cursor_visible(False)
        code_view.add_css_class("card")
        code_view.get_buffer().set_text(_NIRI_BLUR_SNIPPET)
        vbox.append(code_view)

        hint = Gtk.Label(
            label="~/.config/niri/layer-rules.kdl — niri reloads it automatically.",
            xalign=0, wrap=True)
        hint.add_css_class("dim-label")
        vbox.append(hint)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)

        add_btn = Gtk.Button(label="Add to layer-rules.kdl")
        add_btn.add_css_class("suggested-action")
        add_btn.set_sensitive(not already)

        copy_btn = Gtk.Button(icon_name="edit-copy-symbolic")
        copy_btn.set_tooltip_text("Copy layer-rule to clipboard")

        btn_box.append(add_btn)
        btn_box.append(copy_btn)
        vbox.append(btn_box)

        def on_add(_b) -> None:
            from config.gtk_window.toast import toast
            err = _niri_append_config(_NIRI_LAYER_RULES, _NIRI_BLUR_SNIPPET)
            if err:
                toast(f"Failed: {err}")
            else:
                status_stack.set_visible_child_name("ok")
                add_btn.set_sensitive(False)
                toast("Added to layer-rules.kdl — niri will reload automatically.")

        def on_copy(_b) -> None:
            clipboard = copy_btn.get_clipboard()
            if clipboard:
                clipboard.set(_NIRI_BLUR_SNIPPET)
            from config.gtk_window.toast import toast
            toast("Layer-rule copied")

        add_btn.connect("clicked", on_add)
        copy_btn.connect("clicked", on_copy)

        row.set_child(vbox)
        return row

    def _avatar_row(self, vars: Vars) -> Gtk.Widget:
        """Avatar image path (shown beside the chat bubble and on the
        companion's notifications). Blank falls back to the pack icon. A Browse
        button opens a file picker."""
        row = AdwEntryRow("Avatar image", vars.companion_avatar)
        browse = Gtk.Button(icon_name="document-open-symbolic", valign=Gtk.Align.CENTER)
        browse.set_tooltip_text("Choose an image (blank = use the pack icon)")
        browse.add_css_class("flat")
        row.add_suffix(browse)

        def on_selected(fd, result, _ud) -> None:
            try:
                file = fd.open_finish(result)
            except Exception:
                return
            if file:
                vars.companion_avatar.set(file.get_path())

        def on_browse(_b) -> None:
            fd = Gtk.FileDialog.new()
            fd.set_title("Choose Companion Avatar")
            filt = Gtk.FileFilter()
            filt.set_name("Image files")
            for mime in ("image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"):
                filt.add_mime_type(mime)
            fd.set_default_filter(filt)
            fd.open(self.get_root(), None, on_selected, None)
        browse.connect("clicked", on_browse)
        return row

    def _model_picker(self, vars: Vars, target_var, backend_var=None, *,
                      subtitle: str = "Detected models for the selected backend") -> Gtk.Widget:
        """Detected-models dropdown — see widgets.model_picker (shared with Packs)."""
        from config.gtk_window.widgets import model_picker
        return model_picker(vars, target_var, backend_var, subtitle=subtitle)

    def _memory_facts_editor(self) -> Gtk.Widget:
        """Editor for the learned-memory facts file (one fact per line), with a
        Clear button. Backed directly by the companion memory store."""
        from features.companion import memory
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label="Learned facts (one per line)", xalign=0, hexpand=True)
        label.add_css_class("dim-label")
        clear_btn = Gtk.Button(label="Clear")
        clear_btn.add_css_class("destructive-action")
        header.append(label)
        header.append(clear_btn)
        box.append(header)

        view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False)
        for m in ("top", "bottom", "left", "right"):
            getattr(view, f"set_{m}_margin")(6)
        buf = view.get_buffer()
        buf.set_text("\n".join(memory.load_facts()))

        def on_changed(b) -> None:
            text = b.get_text(b.get_start_iter(), b.get_end_iter(), False)
            memory.save_facts([ln for ln in text.splitlines() if ln.strip()])
        buf.connect("changed", on_changed)

        def on_clear(_b) -> None:
            memory.clear()
            buf.set_text("")
        clear_btn.connect("clicked", on_clear)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(100)
        scroller.set_child(view)
        frame = Gtk.Frame()
        frame.add_css_class("card")
        frame.set_child(scroller)
        box.append(frame)
        return box

    def _on_test(self, _btn: Gtk.Button) -> None:
        from features.companion.engine import _DEFAULT_SYSTEM
        from config.gtk_window.widgets import _slot_connection
        backend = self._vars.companion_backend.get() or "scripted"
        url, key = _slot_connection(self._vars, backend)
        model = self._vars.companion_model.get() or ""
        # Use the configured persona prompt so Test previews the real companion;
        # fall back to the built-in default when left blank.
        prompt = (self._vars.companion_system_prompt.get() or "").strip() or _DEFAULT_SYSTEM
        self._reply.set_text("")
        self._test_btn.set_sensitive(False)
        self._spinner.set_visible(True)
        threading.Thread(target=self._test_worker, args=(backend, url, model, key, prompt), daemon=True).start()

    def _test_worker(self, backend: str, url: str, model: str, key: str, prompt: str) -> None:
        client = llm.make_backend(
            backend, base_url=url, model=model, api_key=(key or None),
            scripted_corpus=["Hello! (scripted mode — no AI backend in use.)"])
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "(greeting) Greet your pet in one short line."},
        ]
        acc = {"text": ""}

        def tok(t: str) -> None:
            acc["text"] += t
            GLib.idle_add(self._reply.set_text, acc["text"])

        def done(_full: str) -> None:
            GLib.idle_add(self._finish, acc["text"] or "(no response)")

        def err(e: Exception) -> None:
            GLib.idle_add(self._finish, f"Error: {e}")

        client.stream(messages, tok, done, err)

    def _finish(self, text: str) -> bool:
        self._spinner.set_visible(False)
        self._test_btn.set_sensitive(True)
        self._reply.set_text(text)
        return False
