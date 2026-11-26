"""Main-thread Cocoa status item; no secondary NSApplication loop."""

from __future__ import annotations

from collections.abc import Callable

import AppKit
import objc
from Foundation import NSObject

from .macos_input import require_main_thread
from .resources import asset_path


class VoxenMenuTarget(NSObject):
    @objc.python_method
    def set_callbacks(self, callbacks):
        self.callbacks = callbacks

    def invoke_(self, sender):
        self.callbacks[sender.tag()]()


class MacTray:
    def __init__(self, on_open: Callable, on_pause: Callable, on_quit: Callable):
        self.callbacks = (on_open, on_pause, on_quit)
        self.item = None
        self.target = None

    def start(self) -> None:
        require_main_thread()
        if self.item is not None:
            return
        bar = AppKit.NSStatusBar.systemStatusBar()
        self.item = bar.statusItemWithLength_(AppKit.NSVariableStatusItemLength)
        try:
            image = AppKit.NSImage.alloc().initWithContentsOfFile_(str(asset_path("voxen-mark.png")))
            if image is None or self.item is None or self.item.button() is None:
                raise RuntimeError("Could not initialize macOS menu bar icon.")
            image.setSize_((22, 22))
            image.setTemplate_(True)
            self.item.button().setImage_(image)
            self.item.button().setToolTip_("Voxen")
            self.target = VoxenMenuTarget.alloc().init()
            self.target.set_callbacks(self.callbacks)
            menu = AppKit.NSMenu.alloc().initWithTitle_("Voxen")
            for index, title in enumerate(("Open Voxen", "Pause / Resume", "Quit")):
                if index == 2:
                    menu.addItem_(AppKit.NSMenuItem.separatorItem())
                entry = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, "invoke:", "")
                entry.setTag_(index)
                entry.setTarget_(self.target)
                menu.addItem_(entry)
            self.item.setMenu_(menu)
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        require_main_thread()
        if self.item is not None:
            AppKit.NSStatusBar.systemStatusBar().removeStatusItem_(self.item)
        self.item = self.target = None
