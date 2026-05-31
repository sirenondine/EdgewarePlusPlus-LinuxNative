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

"""Native StatusNotifierItem (freedesktop/KDE tray spec) over D-Bus.

Replaces AppIndicator3, which is GTK3-only and cannot load in our GTK4
process. Works on any Wayland panel that hosts a StatusNotifierWatcher
(KDE, waybar, noctalia, …).

Left click  -> open the companion (else panic, if no companion)
Middle click-> skip to hibernate (when hibernate mode is on)
Right click -> menu (Panic is always here)
"""

import logging
import os
from typing import Callable

from gi.repository import Gio, GLib

_INTROSPECTION = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="u" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="OverlayIconName" type="s" access="read"/>
    <property name="AttentionIconName" type="s" access="read"/>
    <property name="AttentionMovieName" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <method name="Activate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="ContextMenu">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="Scroll">
      <arg name="delta" type="i" direction="in"/>
      <arg name="orientation" type="s" direction="in"/>
    </method>
    <signal name="NewIcon"/>
    <signal name="NewAttentionIcon"/>
    <signal name="NewOverlayIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus">
      <arg name="status" type="s"/>
    </signal>
  </interface>
</node>
"""

_DBUSMENU_INTROSPECTION = """
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="Status" type="s" access="read"/>
    <method name="GetLayout">
      <arg type="i" name="parentId" direction="in"/>
      <arg type="i" name="recursionDepth" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="u" name="revision" direction="out"/>
      <arg type="(ia{sv}av)" name="layout" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="a(ia{sv})" name="properties" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="name" direction="in"/>
      <arg type="v" name="value" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="eventId" direction="in"/>
      <arg type="v" name="data" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" name="id" direction="in"/>
      <arg type="b" name="needUpdate" direction="out"/>
    </method>
    <signal name="ItemsPropertiesUpdated">
      <arg type="a(ia{sv})" name="updatedProps"/>
      <arg type="a(ias)" name="removedProps"/>
    </signal>
    <signal name="LayoutUpdated">
      <arg type="u" name="revision"/>
      <arg type="i" name="parent"/>
    </signal>
    <signal name="ItemActivationRequested">
      <arg type="i" name="id"/>
      <arg type="u" name="timestamp"/>
    </signal>
  </interface>
</node>
"""

_WATCHER_NAME = "org.kde.StatusNotifierWatcher"
_WATCHER_PATH = "/StatusNotifierWatcher"
_ITEM_PATH = "/StatusNotifierItem"
_MENU_PATH = "/MenuBar"


class DBusMenu:
    """Minimal com.canonical.dbusmenu — a flat list of action items."""

    def __init__(self, conn: Gio.DBusConnection, iface, items: list[tuple[str, Callable[[], None]]]) -> None:
        # items: list of (label, callback); ids are 1-based index.
        self._items = items
        self._visible = [True] * len(items)
        self._conn = conn
        self._revision = 1
        self.reg_id = conn.register_object(
            _MENU_PATH, iface, self._on_method_call, self._on_get_property, None
        )

    def set_item_visible(self, index: int, visible: bool) -> None:
        if not (0 <= index < len(self._items)) or self._visible[index] == visible:
            return
        self._visible[index] = visible
        self._revision += 1
        try:
            self._conn.emit_signal(
                None, _MENU_PATH, "com.canonical.dbusmenu", "LayoutUpdated",
                GLib.Variant("(ui)", (self._revision, 0)))
        except Exception:
            pass

    def set_item_label(self, index: int, label: str) -> None:
        """Relabel an item in place and tell the host to re-fetch the layout."""
        if not (0 <= index < len(self._items)):
            return
        self._items[index] = (label, self._items[index][1])
        self._revision += 1
        try:
            self._conn.emit_signal(
                None, _MENU_PATH, "com.canonical.dbusmenu", "LayoutUpdated",
                GLib.Variant("(ui)", (self._revision, 0)))
        except Exception:
            pass

    def _item_props(self, index: int) -> dict:
        return {
            "label": GLib.Variant("s", self._items[index][0]),
            "enabled": GLib.Variant("b", True),
            "visible": GLib.Variant("b", self._visible[index]),
        }

    def _layout_tuple(self) -> tuple:
        children = [
            GLib.Variant("(ia{sv}av)", (i + 1, self._item_props(i), []))
            for i in range(len(self._items))
        ]
        return (0, {"children-display": GLib.Variant("s", "submenu")}, children)

    def _on_method_call(self, conn, sender, path, iface, method, params, invocation) -> None:
        if method == "GetLayout":
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (self._revision, self._layout_tuple())))
        elif method == "GetGroupProperties":
            ids, _names = params.unpack()
            wanted = ids or [i + 1 for i in range(len(self._items))]
            out = []
            for item_id in wanted:
                if 1 <= item_id <= len(self._items):
                    out.append((item_id, self._item_props(item_id - 1)))
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (out,)))
        elif method == "GetProperty":
            item_id, name = params.unpack()
            props = self._item_props(item_id - 1) if 1 <= item_id <= len(self._items) else {}
            invocation.return_value(GLib.Variant("(v)", (props.get(name, GLib.Variant("s", "")),)))
        elif method == "Event":
            item_id, event_id, _data, _ts = params.unpack()
            invocation.return_value(None)
            # Run directly (not via idle_add) so it fires the moment the click
            # is dispatched — under a popup flood the main loop may have no idle
            # time, and panic must not depend on that.
            if event_id == "clicked" and 1 <= item_id <= len(self._items):
                self._items[item_id - 1][1]()
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        else:
            invocation.return_value(None)

    def _on_get_property(self, conn, sender, path, iface, prop):
        if prop == "Version":
            return GLib.Variant("u", 3)
        if prop == "Status":
            return GLib.Variant("s", "normal")
        return None


class StatusNotifierItem:
    def __init__(self, icon_name: str, tooltip: str, on_panic: Callable[[], None], on_skip_hibernate: Callable[[], None] | None = None, on_open_config: Callable[[], None] | None = None, on_toggle_pause: Callable[[], None] | None = None, on_reconnect_toy: Callable[[], None] | None = None, on_quit: Callable[[], None] | None = None, quit_hidden: bool = False, on_activate: Callable[[], None] | None = None) -> None:
        self._icon_name = icon_name
        self._tooltip = tooltip
        self._on_panic = on_panic
        self._on_activate = on_activate
        self._on_skip_hibernate = on_skip_hibernate
        self._on_open_config = on_open_config
        self._on_toggle_pause = on_toggle_pause
        self._on_reconnect_toy = on_reconnect_toy
        self._on_quit = on_quit
        self._quit_hidden = quit_hidden
        self._reg_id = 0
        self._menu = None
        self._owner_id = 0
        self._conn: Gio.DBusConnection | None = None
        self._bus_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"

        self._iface = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION).interfaces[0]
        self._menu_iface = Gio.DBusNodeInfo.new_for_xml(_DBUSMENU_INTROSPECTION).interfaces[0]

        # Build the right-click menu model.
        self._menu_items: list[tuple[str, Callable[[], None]]] = [("Panic", on_panic)]
        self._pause_index: int | None = None
        if on_toggle_pause:
            self._pause_index = len(self._menu_items)
            self._menu_items.append(("Pause Popups", on_toggle_pause))
        self._toy_index: int | None = None
        if on_reconnect_toy:
            self._toy_index = len(self._menu_items)
            self._menu_items.append(("Toy: connecting…", on_reconnect_toy))
        if on_skip_hibernate:
            self._menu_items.append(("Skip to Hibernate", on_skip_hibernate))
        if on_open_config:
            self._menu_items.append(("Open Config", on_open_config))
        self._quit_index: int | None = None
        if on_quit:
            self._quit_index = len(self._menu_items)
            self._menu_items.append(("Quit", on_quit))

        self._owner_id = Gio.bus_own_name(
            Gio.BusType.SESSION,
            self._bus_name,
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired,
            None,
            self._on_name_lost,
        )

    def _on_bus_acquired(self, conn: Gio.DBusConnection, name: str) -> None:
        self._conn = conn
        try:
            self._reg_id = conn.register_object(
                _ITEM_PATH,
                self._iface,
                self._on_method_call,
                self._on_get_property,
                None,
            )
            self._menu = DBusMenu(conn, self._menu_iface, self._menu_items)
            if self._quit_hidden and self._quit_index is not None:
                self._menu.set_item_visible(self._quit_index, False)
        except Exception as e:
            logging.warning(f"Failed to export StatusNotifierItem: {e}")
            return
        self._register_with_watcher()

    def _on_name_lost(self, conn: Gio.DBusConnection, name: str) -> None:
        logging.info("StatusNotifierItem lost its bus name.")

    def _register_with_watcher(self) -> None:
        def done(src, res):
            try:
                src.call_finish(res)
            except Exception as e:
                logging.info(f"No StatusNotifierWatcher to register with: {e}")

        self._conn.call(
            _WATCHER_NAME, _WATCHER_PATH, _WATCHER_NAME,
            "RegisterStatusNotifierItem",
            GLib.Variant("(s)", (self._bus_name,)),
            None, Gio.DBusCallFlags.NONE, -1, None, done,
        )

    def _on_method_call(self, conn, sender, path, iface, method, params, invocation) -> None:
        invocation.return_value(None)
        # Left click (Activate): open the companion if wired, else panic. Panic
        # runs directly so it still works when the main loop is busy.
        if method == "Activate":
            if self._on_activate:
                self._on_activate()
            else:
                self._on_panic()
        elif method == "SecondaryActivate":
            if self._on_skip_hibernate:
                self._on_skip_hibernate()

    def _on_get_property(self, conn, sender, path, iface, prop):
        values = {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", "edgeware"),
            "Title": GLib.Variant("s", "Edgeware++"),
            "Status": GLib.Variant("s", "Active"),
            "WindowId": GLib.Variant("u", 0),
            "IconName": GLib.Variant("s", self._icon_name),
            "IconThemePath": GLib.Variant("s", ""),
            "OverlayIconName": GLib.Variant("s", ""),
            "AttentionIconName": GLib.Variant("s", ""),
            "AttentionMovieName": GLib.Variant("s", ""),
            "IconPixmap": GLib.Variant("a(iiay)", []),
            "ToolTip": GLib.Variant("(sa(iiay)ss)", ("", [], "Edgeware++", self._tooltip)),
            "ItemIsMenu": GLib.Variant("b", False),
            "Menu": GLib.Variant("o", _MENU_PATH),
        }
        return values.get(prop)

    def set_pause_label(self, paused: bool) -> None:
        """Reflect the current pause state in the tray menu item."""
        if self._menu and self._pause_index is not None:
            self._menu.set_item_label(self._pause_index, "Resume Popups" if paused else "Pause Popups")

    def set_toy_status(self, connected: bool) -> None:
        """Reflect toy connection state in the tray menu. Clicking the item
        reconnects (a no-op while connected)."""
        if self._menu and self._toy_index is not None:
            self._menu.set_item_label(self._toy_index, "Toy: connected" if connected else "Reconnect toy")

    def set_quit_visible(self, visible: bool) -> None:
        """Show/hide the Quit item (gated behind finishing the daily quests)."""
        if self._menu and self._quit_index is not None:
            self._menu.set_item_visible(self._quit_index, visible)

    def stop(self) -> None:
        if self._conn:
            for reg in (self._reg_id, getattr(self._menu, "reg_id", 0)):
                if reg:
                    try:
                        self._conn.unregister_object(reg)
                    except Exception:
                        pass
            self._reg_id = 0
        if self._owner_id:
            Gio.bus_unown_name(self._owner_id)
            self._owner_id = 0
