"""單一 MCP agent loop 內的唯讀 tool 結果快取（instanceID / 目標物件級）。"""

from __future__ import annotations

import json
import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from core.harness_log import harness_log

_READ_CACHE: ContextVar[McpReadCache | None] = ContextVar("harness_mcp_read_cache", default=None)

# IvanMurzak / unity__ 前綴剝離後比對
_READ_TOOL_PATTERNS = (
    re.compile(r"gameobject-find$", re.I),
    re.compile(r"gameobject-component-get$", re.I),
    re.compile(r"object-get-data$", re.I),
    re.compile(r"scene-get-data$", re.I),
    re.compile(r"scene-list-opened$", re.I),
    re.compile(r"assets?-(find|list|get)", re.I),
)

_WRITE_TOOL_PATTERNS = (
    re.compile(r"gameobject-create", re.I),
    re.compile(r"gameobject-delete", re.I),
    re.compile(r"gameobject-duplicate", re.I),
    re.compile(r"gameobject-component-(add|remove|set|modify)", re.I),
    re.compile(r"script-execute", re.I),
    re.compile(r"assets?-(create|import|delete|move|write)", re.I),
    re.compile(r"scene-(open|save|create|unload)", re.I),
    re.compile(r"-create$", re.I),
    re.compile(r"-delete$", re.I),
    re.compile(r"-set$", re.I),
    re.compile(r"-modify$", re.I),
)


def _tool_basename(tool_name: str) -> str:
    name = (tool_name or "").strip()
    if "__" in name:
        name = name.split("__", 1)[-1]
    return name


def is_read_tool(tool_name: str) -> bool:
    base = _tool_basename(tool_name)
    return any(p.search(base) for p in _READ_TOOL_PATTERNS)


def is_write_tool(tool_name: str) -> bool:
    base = _tool_basename(tool_name)
    if is_read_tool(tool_name):
        return False
    return any(p.search(base) for p in _WRITE_TOOL_PATTERNS)


def _norm_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def _ref_key(ref: Any) -> str | None:
    """將 gameObjectRef / objectRef 正規化為快取用字串。"""
    if ref is None:
        return None
    if isinstance(ref, str) and ref.strip():
        return f"name:{ref.strip()}"
    if not isinstance(ref, dict):
        return None
    iid = ref.get("instanceID")
    if iid is not None and str(iid).strip() not in ("", "0"):
        return f"id:{int(iid) if str(iid).isdigit() else iid}"
    for key in ("name", "Name", "path", "Path"):
        val = ref.get(key)
        if val is not None and str(val).strip():
            raw = str(val).strip()
            # path 常為 Hierarchy 名稱
            leaf = raw.split("/")[-1] if "/" in raw else raw
            return f"name:{leaf}"
    return None


def _component_key(component_ref: Any) -> str | None:
    if not isinstance(component_ref, dict):
        return None
    iid = component_ref.get("instanceID")
    if iid is None or str(iid).strip() in ("", "0"):
        return None
    return f"comp:{int(iid) if str(iid).isdigit() else iid}"


def _detail_score(include_properties: bool, include_fields: bool) -> int:
    return (2 if include_properties else 0) + (1 if include_fields else 0)


@dataclass(frozen=True)
class CacheLookupKey:
    tool_base: str
    primary: str
    secondary: str | None = None
    detail: int = 0

    def covers(self, other: CacheLookupKey) -> bool:
        """已快取項目是否涵蓋新請求（同目標且細度不低）。"""
        return (
            self.tool_base == other.tool_base
            and self.primary == other.primary
            and self.secondary == other.secondary
            and self.detail >= other.detail
        )


@dataclass
class CacheEntry:
    key: CacheLookupKey
    tool_name: str
    serialized_content: str
    raw_for_log: str = ""


@dataclass
class McpReadCache:
    """單次 ``complete_with_mcp_loop`` 生命週期內的有效快取。"""

    entries: list[CacheEntry] = field(default_factory=list)
    hits: int = 0

    def clear(self) -> None:
        self.entries.clear()
        self.hits = 0

    def invalidate_all(self, *, reason: str, tool_name: str) -> None:
        if self.entries:
            harness_log(
                f"[Harness Cache] 寫入工具 {tool_name} → 清除 {len(self.entries)} 筆讀取快取（{reason}）"
            )
        self.entries.clear()

    def lookup(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> CacheEntry | None:
        key = build_lookup_key(tool_name, arguments)
        if key is None:
            return None
        for entry in reversed(self.entries):
            if entry.key.covers(key):
                return entry
        return None

    def store(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        serialized_content: str,
    ) -> None:
        key = build_lookup_key(tool_name, arguments)
        if key is None or not serialized_content.strip():
            return
        # 過濾預期錯誤 / fatal JSON，不進快取
        try:
            data = json.loads(serialized_content)
            if isinstance(data, dict) and data.get("status") in (
                "expected_not_found",
                "system_fatal_error",
                "harness_cache_hit",
            ):
                return
        except json.JSONDecodeError:
            pass
        # 以較細的 detail 覆寫同 key 的舊項
        self.entries = [e for e in self.entries if not e.key.covers(key)]
        self.entries.append(
            CacheEntry(
                key=key,
                tool_name=tool_name,
                serialized_content=serialized_content,
            )
        )


def build_lookup_key(
    tool_name: str,
    arguments: dict[str, Any],
) -> CacheLookupKey | None:
    base = _tool_basename(tool_name)
    args = arguments or {}

    if re.search(r"gameobject-find$", base, re.I):
        go = _ref_key(args.get("gameObjectRef"))
        if not go:
            return None
        detail = 0
        if _norm_bool(args.get("includeComponents")):
            detail += 2
        if _norm_bool(args.get("includeData")):
            detail += 1
        return CacheLookupKey("find", go, None, detail)

    if re.search(r"gameobject-component-get$", base, re.I):
        go = _ref_key(args.get("gameObjectRef"))
        comp = _component_key(args.get("componentRef"))
        if not go or not comp:
            return None
        detail = _detail_score(
            _norm_bool(args.get("includeProperties")),
            _norm_bool(args.get("includeFields")),
        )
        return CacheLookupKey("component-get", go, comp, detail)

    if re.search(r"object-get-data$", base, re.I):
        obj = _ref_key(args.get("objectRef"))
        if not obj:
            return None
        return CacheLookupKey("object-get", obj, None, 0)

    if re.search(r"scene-get-data$", base, re.I):
        scene = str(args.get("openedSceneName") or args.get("scenePath") or "").strip()
        if not scene:
            return None
        return CacheLookupKey("scene-get", scene, None, 0)

    if re.search(r"scene-list-opened$", base, re.I):
        return CacheLookupKey("scene-list", "opened", None, 0)

    return None


def wrap_cache_hit_content(entry: CacheEntry) -> str:
    """在 tool 回覆前加上 Harness 標記，供模型辨識為同 loop 內重複讀取。"""
    try:
        inner = json.loads(entry.serialized_content)
    except json.JSONDecodeError:
        inner = entry.serialized_content
    payload = {
        "harness_cache_hit": True,
        "harness_notice": (
            "Duplicate read in this task MCP loop; reusing cached tool result. "
            "Do not repeat the same read — use this data or perform a write if needed."
        ),
        "cached_tool": entry.tool_name,
        "cached_key": {
            "primary": entry.key.primary,
            "secondary": entry.key.secondary,
            "detail": entry.key.detail,
        },
        "result": inner,
    }
    return json.dumps(payload, ensure_ascii=False)


def get_active_read_cache() -> McpReadCache | None:
    return _READ_CACHE.get()


def reset_read_cache() -> McpReadCache:
    cache = McpReadCache()
    _READ_CACHE.set(cache)
    return cache


def clear_read_cache() -> None:
    _READ_CACHE.set(None)


def try_cache_read(
    tool_name: str,
    arguments: dict[str, Any],
) -> str | None:
    """若命中快取回傳 serialized content；否則 None。"""
    if not is_read_tool(tool_name):
        return None
    cache = get_active_read_cache()
    if cache is None:
        return None
    entry = cache.lookup(tool_name, arguments)
    if entry is None:
        return None
    cache.hits += 1
    key = build_lookup_key(tool_name, arguments)
    label = entry.key.primary
    if entry.key.secondary:
        label = f"{label} {entry.key.secondary}"
    harness_log(
        f"[Harness Cache] 略過重複唯讀 MCP（{tool_name} → {label}，detail<={entry.key.detail}）"
    )
    return wrap_cache_hit_content(entry)


def record_read_result(
    tool_name: str,
    arguments: dict[str, Any],
    serialized_content: str,
) -> None:
    if not is_read_tool(tool_name):
        return
    cache = get_active_read_cache()
    if cache is None:
        return
    cache.store(tool_name, arguments, serialized_content)


def on_write_tool(tool_name: str, arguments: dict[str, Any]) -> None:
    if not is_write_tool(tool_name):
        return
    cache = get_active_read_cache()
    if cache is None:
        return
    # 若參數能解析目標物件，可只清相關項；保守起見整批清除
    cache.invalidate_all(reason="Editor 可能已變更", tool_name=tool_name)
