from __future__ import annotations

import sys
import time
from collections.abc import Callable, Sequence
from typing import Protocol


class ClipboardBackend(Protocol):
    def snapshot(self):
        ...

    def set_text(self, text: str) -> None:
        ...

    def restore(self, snapshot) -> None:
        ...


class PlainTextClipboardBackend:
    def __init__(self, clipboard) -> None:
        self._clipboard = clipboard

    def snapshot(self):
        try:
            return self._clipboard.paste()
        except Exception:
            return None

    def set_text(self, text: str) -> None:
        self._clipboard.copy(text)

    def restore(self, snapshot) -> None:
        if snapshot is not None:
            self._clipboard.copy(snapshot)


class WindowsClipboardBackend:
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Il backend clipboard Windows richiede Windows.")
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._user32.OpenClipboard.argtypes = [wintypes.HWND]
        self._user32.OpenClipboard.restype = wintypes.BOOL
        self._user32.CloseClipboard.argtypes = []
        self._user32.CloseClipboard.restype = wintypes.BOOL
        self._user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
        self._user32.EnumClipboardFormats.restype = wintypes.UINT
        self._user32.GetClipboardData.argtypes = [wintypes.UINT]
        self._user32.GetClipboardData.restype = wintypes.HANDLE
        self._user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        self._user32.SetClipboardData.restype = wintypes.HANDLE
        self._user32.EmptyClipboard.argtypes = []
        self._user32.EmptyClipboard.restype = wintypes.BOOL
        self._kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
        self._kernel32.GlobalSize.restype = ctypes.c_size_t
        self._kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        self._kernel32.GlobalLock.restype = ctypes.c_void_p
        self._kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        self._kernel32.GlobalUnlock.restype = wintypes.BOOL
        self._kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        self._kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        self._kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        self._kernel32.GlobalFree.restype = wintypes.HGLOBAL

    def _open(self) -> None:
        if not self._user32.OpenClipboard(None):
            raise RuntimeError("Impossibile aprire il clipboard di Windows.")

    def snapshot(self) -> Sequence[tuple[int, bytes]] | None:
        self._open()
        formats = []
        try:
            clipboard_format = 0
            while True:
                clipboard_format = self._user32.EnumClipboardFormats(clipboard_format)
                if not clipboard_format:
                    break
                handle = self._user32.GetClipboardData(clipboard_format)
                if not handle:
                    continue
                size = self._kernel32.GlobalSize(handle)
                pointer = self._kernel32.GlobalLock(handle)
                if not pointer:
                    continue
                try:
                    formats.append((clipboard_format, self._ctypes.string_at(pointer, size)))
                finally:
                    self._kernel32.GlobalUnlock(handle)
            return formats
        finally:
            self._user32.CloseClipboard()

    def _set_format(self, clipboard_format: int, data: bytes) -> None:
        handle = self._kernel32.GlobalAlloc(self.GMEM_MOVEABLE, len(data))
        if not handle:
            raise RuntimeError("Memoria insufficiente per ripristinare il clipboard.")
        pointer = self._kernel32.GlobalLock(handle)
        if not pointer:
            self._kernel32.GlobalFree(handle)
            raise RuntimeError("Impossibile preparare il clipboard di Windows.")
        try:
            self._ctypes.memmove(pointer, data, len(data))
        finally:
            self._kernel32.GlobalUnlock(handle)
        if not self._user32.SetClipboardData(clipboard_format, handle):
            self._kernel32.GlobalFree(handle)
            raise RuntimeError("Impossibile ripristinare il clipboard di Windows.")

    def set_text(self, text: str) -> None:
        data = text.encode("utf-16-le") + b"\x00\x00"
        self._open()
        try:
            if not self._user32.EmptyClipboard():
                raise RuntimeError("Impossibile svuotare il clipboard di Windows.")
            self._set_format(self.CF_UNICODETEXT, data)
        finally:
            self._user32.CloseClipboard()

    def restore(self, snapshot: Sequence[tuple[int, bytes]] | None) -> None:
        if snapshot is None:
            return
        self._open()
        try:
            if not self._user32.EmptyClipboard():
                raise RuntimeError("Impossibile svuotare il clipboard di Windows.")
            for clipboard_format, data in snapshot:
                self._set_format(clipboard_format, data)
        finally:
            self._user32.CloseClipboard()


class MacOSClipboardBackend:
    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("Il backend clipboard macOS richiede macOS.")
        try:
            import AppKit
            from Foundation import NSData
        except ImportError as exc:
            raise RuntimeError("PyObjC non è disponibile per il clipboard macOS.") from exc
        self._appkit = AppKit
        self._data_class = NSData
        self._pasteboard = AppKit.NSPasteboard.generalPasteboard()

    def snapshot(self):
        items = self._pasteboard.pasteboardItems() or []
        snapshot = []
        for item in items:
            formats = []
            for type_name in item.types() or []:
                data = item.dataForType_(type_name)
                if data is not None:
                    formats.append((str(type_name), bytes(data)))
            snapshot.append(formats)
        return snapshot

    def set_text(self, text: str) -> None:
        self._pasteboard.clearContents()
        string_type = getattr(self._appkit, "NSPasteboardTypeString", None)
        if string_type is None:
            string_type = self._appkit.NSStringPboardType
        if not self._pasteboard.setString_forType_(text, string_type):
            raise RuntimeError("Impossibile impostare il testo nel clipboard macOS.")

    def restore(self, snapshot) -> None:
        self._pasteboard.clearContents()
        items = []
        for formats in snapshot:
            item = self._appkit.NSPasteboardItem.alloc().init()
            for type_name, data in formats:
                native_data = self._data_class.dataWithBytes_length_(data, len(data))
                item.setData_forType_(native_data, type_name)
            items.append(item)
        if items and not self._pasteboard.writeObjects_(items):
            raise RuntimeError("Impossibile ripristinare il clipboard macOS.")


class ClipboardInjector:
    def __init__(
        self,
        paste_delay: float = 0.05,
        restore_delay: float = 0.15,
        sleep: Callable[[float], None] = time.sleep,
        clipboard=None,
        automation=None,
        backend: ClipboardBackend | None = None,
    ) -> None:
        self.paste_delay = paste_delay
        self.restore_delay = restore_delay
        self._sleep = sleep
        self._clipboard = clipboard
        self._automation = automation
        self._backend = backend

    def _get_backend(self) -> ClipboardBackend:
        if self._backend is not None:
            return self._backend
        try:
            import pyperclip
        except ImportError as exc:
            raise RuntimeError("Installa pyperclip per incollare il testo.") from exc
        if self._clipboard is not None:
            return PlainTextClipboardBackend(self._clipboard)
        if sys.platform == "win32":
            try:
                return WindowsClipboardBackend()
            except (ImportError, OSError, RuntimeError):
                pass
        if sys.platform == "darwin":
            try:
                return MacOSClipboardBackend()
            except (ImportError, OSError, RuntimeError):
                pass
        return PlainTextClipboardBackend(pyperclip)

    def inject(self, text: str) -> None:
        backend = self._get_backend()
        automation = self._automation
        if automation is None:
            try:
                import pyautogui
            except ImportError as exc:
                raise RuntimeError("Installa pyautogui per incollare il testo.") from exc
            automation = automation or pyautogui

        previous = backend.snapshot()
        restore_needed = previous is not None

        operation_error = None
        try:
            backend.set_text(text)
            self._sleep(self.paste_delay)
            paste_modifier = "command" if sys.platform == "darwin" else "ctrl"
            automation.hotkey(paste_modifier, "v")
            self._sleep(self.restore_delay)
        except Exception as exc:
            operation_error = exc
        finally:
            if restore_needed:
                try:
                    backend.restore(previous)
                except Exception as exc:
                    if operation_error is None:
                        operation_error = exc

        if operation_error is not None:
            raise RuntimeError(f"Impossibile incollare il testo: {operation_error}") from operation_error
