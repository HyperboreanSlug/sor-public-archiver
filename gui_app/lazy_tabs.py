"""Lazy tab host: build tab body on first selection (or idle warm)."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


class LazyTabHost:
    """CTkTabview wrapper: first selection builds tab body once.

    CustomTkinter tab bodies are expensive (many canvas widgets). Prefer
    ``warm()`` during idle so the user's first click does not wait on build.
    """

    def __init__(self, tabview: Any, on_change: Optional[Callable] = None):
        self.tabview = tabview
        self._loaders: Dict[str, Callable] = {}
        self._loaded: Dict[str, Any] = {}
        self._on_change = on_change
        try:
            tabview.configure(command=self._handle_change)
        except Exception:
            pass

    def register(self, name: str, loader: Callable) -> None:
        """loader(parent) builds widgets into parent; return value is stored as controller."""
        self.tabview.add(name)
        self._loaders[name] = loader

    def names(self) -> List[str]:
        return list(self._loaders.keys())

    def _build_once(self, name: str) -> Any:
        """Create tab body if missing; no on_change side effects."""
        if name in self._loaded:
            return self._loaded[name]
        if name not in self._loaders:
            return None
        parent = self.tabview.tab(name)
        self._loaded[name] = self._loaders[name](parent)
        return self._loaded[name]

    def warm(self, name: str) -> Any:
        """Build tab in the background without switching focus or on_change."""
        try:
            return self._build_once(name)
        except Exception:
            return None

    def _handle_change(self, name: Optional[str] = None) -> None:
        try:
            name = name or self.tabview.get()
        except Exception:
            return
        if name not in self._loaded and name in self._loaders:
            try:
                self._build_once(name)
            except Exception:
                pass
        if self._on_change:
            try:
                self._on_change(name)
            except Exception:
                pass

    def ensure(self, name: str) -> Any:
        """Force-load a tab (e.g. default landing tab) and fire on_change."""
        self._handle_change(name)
        return self._loaded.get(name)

    def get_controller(self, name: str) -> Any:
        return self._loaded.get(name)

    def is_loaded(self, name: str) -> bool:
        return name in self._loaded
