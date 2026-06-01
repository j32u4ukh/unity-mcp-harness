"""對話模式共用設定（Gemini 等長上下文模型）。"""

from __future__ import annotations

# 單則助理/使用者訊息寫入 state.history 的上限（字元）
DIALOGUE_HISTORY_ENTRY_MAX_CHARS = 16_000

# state.history 保留的則數（/write 摘要等仍會引用）
DIALOGUE_HISTORY_MAX_ENTRIES = 48
