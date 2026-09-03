from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import sys


class SystemTray:
    def __init__(self, on_open: Callable[[], None], on_pause: Callable[[], None], on_quit: Callable[[], None]) -> None:
        self.on_open = on_open
        self.on_pause = on_pause
        self.on_quit = on_quit
        self._icon = None
        self._thread = None

    def start(self) -> None:
        try:
            import pystray
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Installa pystray e Pillow per usare la system tray.") from exc

        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
        icon_path = root / "assets" / "voxen-mark.png"
        if not icon_path.exists():
            raise RuntimeError(f"Asset tray non trovato: {icon_path}")
        image = Image.open(icon_path)
        menu = pystray.Menu(
            pystray.MenuItem("Open Voxen", lambda _icon, _item: self.on_open()),
            pystray.MenuItem("Pause / Resume", lambda _icon, _item: self.on_pause()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda _icon, _item: self.on_quit()),
        )
        self._icon = pystray.Icon("voxen", image, "Voxen", menu)
        import threading
        self._thread = threading.Thread(target=self._icon.run, name="voxen-tray", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()
            self._icon = None
