"""規劃期補充 prompt：自 JSON 匹配模糊任務並注入，支援互動澄清與寫回。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.pipeline.schema import NormalizedPlan, NormalizedTask
from tasks import BuildPlan, BuildTask

SUPPLEMENT_MARKER_PREFIX = "【規劃補充："
DEFAULT_SUPPLEMENTS_FILENAME = "prompt_supplements.json"


def default_supplements_path() -> Path:
    from unity_common import project_root

    return project_root() / "config" / DEFAULT_SUPPLEMENTS_FILENAME


@dataclass
class PromptSupplement:
    id: str
    description: str = ""
    match_keywords: list[str] = field(default_factory=list)
    match_task_id_substrings: list[str] = field(default_factory=list)
    prompt_block: str = ""
    expected: dict[str, Any] = field(default_factory=dict)
    harness_pre_read: str | None = None
    harness_post_read: str | None = None
    source: str = "builtin"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptSupplement:
        return cls(
            id=str(data["id"]),
            description=str(data.get("description") or ""),
            match_keywords=[str(x) for x in data.get("match_keywords") or []],
            match_task_id_substrings=[str(x) for x in data.get("match_task_id_substrings") or []],
            prompt_block=str(data.get("prompt_block") or "").strip(),
            expected=dict(data.get("expected") or {}),
            harness_pre_read=data.get("harness_pre_read"),
            harness_post_read=data.get("harness_post_read"),
            source=str(data.get("source") or "builtin"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "description": self.description,
            "match_keywords": self.match_keywords,
            "match_task_id_substrings": self.match_task_id_substrings,
            "prompt_block": self.prompt_block,
        }
        if self.expected:
            out["expected"] = self.expected
        if self.harness_pre_read:
            out["harness_pre_read"] = self.harness_pre_read
        if self.harness_post_read:
            out["harness_post_read"] = self.harness_post_read
        if self.source != "builtin":
            out["source"] = self.source
        return out


@dataclass
class ClarificationTemplate:
    id: str
    question: str
    when_keywords: list[str] = field(default_factory=list)
    when_task_id_substrings: list[str] = field(default_factory=list)
    unless_supplement_ids: list[str] = field(default_factory=list)
    unless_task_keywords: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClarificationTemplate:
        return cls(
            id=str(data["id"]),
            question=str(data["question"]),
            when_keywords=[str(x) for x in data.get("when_keywords") or []],
            when_task_id_substrings=[str(x) for x in data.get("when_task_id_substrings") or []],
            unless_supplement_ids=[str(x) for x in data.get("unless_supplement_ids") or []],
            unless_task_keywords=[str(x) for x in data.get("unless_task_keywords") or []],
        )


@dataclass
class PromptSupplementsDocument:
    version: int = 1
    supplements: list[PromptSupplement] = field(default_factory=list)
    clarification_templates: list[ClarificationTemplate] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptSupplementsDocument:
        supplements = [
            PromptSupplement.from_dict(item)
            for item in data.get("supplements") or []
            if isinstance(item, dict) and item.get("id")
        ]
        templates = [
            ClarificationTemplate.from_dict(item)
            for item in data.get("clarification_templates") or []
            if isinstance(item, dict) and item.get("id")
        ]
        return cls(
            version=int(data.get("version", 1)),
            supplements=supplements,
            clarification_templates=templates,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "supplements": [s.to_dict() for s in self.supplements],
            "clarification_templates": [
                {
                    "id": t.id,
                    "question": t.question,
                    "when_keywords": t.when_keywords,
                    "when_task_id_substrings": t.when_task_id_substrings,
                    "unless_supplement_ids": t.unless_supplement_ids,
                    "unless_task_keywords": t.unless_task_keywords,
                }
                for t in self.clarification_templates
            ],
        }


def load_prompt_supplements(path: Path | str | None = None) -> PromptSupplementsDocument:
    p = Path(path) if path is not None else default_supplements_path()
    if not p.is_file():
        return PromptSupplementsDocument()
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"prompt_supplements 須為 JSON 物件: {p}")
    return PromptSupplementsDocument.from_dict(data)


def save_prompt_supplements(
    document: PromptSupplementsDocument,
    path: Path | str | None = None,
) -> Path:
    p = Path(path) if path is not None else default_supplements_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(
        json.dumps(document.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(p)
    return p


def _task_search_text(task: NormalizedTask | BuildTask) -> str:
    parts = [
        getattr(task, "id", ""),
        getattr(task, "title", "") or "",
        getattr(task, "description", "") or "",
        getattr(task, "prompt", "") or "",
        getattr(task, "objective", "") or "",
    ]
    return "\n".join(str(p) for p in parts if p).lower()


def _keyword_hit(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    return any(k.lower() in text for k in keywords)


def _task_id_hit(task_id: str, substrings: list[str]) -> bool:
    if not substrings:
        return True
    tid = task_id.lower()
    return any(s.lower() in tid for s in substrings)


def match_supplements_for_task(
    task: NormalizedTask | BuildTask,
    document: PromptSupplementsDocument,
) -> list[PromptSupplement]:
    text = _task_search_text(task)
    task_id = getattr(task, "id", "")
    matched: list[PromptSupplement] = []
    for sup in document.supplements:
        if not sup.prompt_block:
            continue
        if not _keyword_hit(text, sup.match_keywords):
            continue
        if not _task_id_hit(task_id, sup.match_task_id_substrings):
            continue
        matched.append(sup)
    return matched


def supplement_marker(supplement_id: str) -> str:
    return f"{SUPPLEMENT_MARKER_PREFIX}{supplement_id}】"


def _prompt_has_supplement(prompt: str, supplement_id: str) -> bool:
    return supplement_marker(supplement_id) in prompt


def inject_supplement_into_task(task: NormalizedTask, supplement: PromptSupplement) -> None:
    if _prompt_has_supplement(task.prompt, supplement.id):
        return
    block = f"\n\n{supplement_marker(supplement.id)}\n{supplement.prompt_block.strip()}\n"
    task.prompt = task.prompt.rstrip() + block
    if supplement.expected:
        merged = dict(task.expected)
        merged.update(supplement.expected)
        task.expected = merged
    if supplement.harness_pre_read and not task.harness.pre_read:
        task.harness.pre_read = supplement.harness_pre_read
    if supplement.harness_post_read and not task.harness.post_read:
        task.harness.post_read = supplement.harness_post_read


def apply_prompt_supplements(
    normalized: NormalizedPlan,
    document: PromptSupplementsDocument,
) -> list[str]:
    """將匹配到的補充片段注入 normalized 任務；回傳已注入的 supplement id 列表。"""
    injected: list[str] = []
    for task in normalized.normalized_tasks:
        for sup in match_supplements_for_task(task, document):
            if _prompt_has_supplement(task.prompt, sup.id):
                continue
            inject_supplement_into_task(task, sup)
            injected.append(sup.id)
    return injected


def collect_matched_supplements_for_plan(
    build_plan: BuildPlan,
    normalized: NormalizedPlan,
    document: PromptSupplementsDocument,
) -> dict[str, list[PromptSupplement]]:
    """依藍圖與規範化任務收集 supplement（供 Normalize user prompt 參考）。"""
    by_id: dict[str, PromptSupplement] = {}
    for task in build_plan.enabled_tasks():
        for sup in match_supplements_for_task(task, document):
            by_id[sup.id] = sup
    for task in normalized.normalized_tasks:
        for sup in match_supplements_for_task(task, document):
            by_id[sup.id] = sup
    return {"all": list(by_id.values())}


def format_supplements_for_normalize_prompt(supplements: list[PromptSupplement]) -> str:
    if not supplements:
        return ""
    lines = [
        "【規劃補充片段（JSON 匹配；請併入相關任務 prompt，勿自行發明未列出的領域規則）】",
    ]
    for sup in supplements:
        lines.append(f"\n--- supplement_id: {sup.id} ---")
        if sup.description:
            lines.append(f"說明：{sup.description}")
        lines.append(sup.prompt_block)
        if sup.expected:
            lines.append(f"建議 expected 欄位：{json.dumps(sup.expected, ensure_ascii=False)}")
    return "\n".join(lines)


def find_open_clarifications(
    build_plan: BuildPlan,
    normalized: NormalizedPlan,
    document: PromptSupplementsDocument,
) -> list[tuple[ClarificationTemplate, str]]:
    """回傳 (template, task_id) 需向人類確認的項目。"""
    open_items: list[tuple[ClarificationTemplate, str]] = []
    seen: set[str] = set()

    def _check_task(task_id: str, text: str) -> None:
        for tmpl in document.clarification_templates:
            key = f"{tmpl.id}:{task_id}"
            if key in seen:
                continue
            if tmpl.when_task_id_substrings and not _task_id_hit(task_id, tmpl.when_task_id_substrings):
                continue
            if not _keyword_hit(text, tmpl.when_keywords):
                continue
            if tmpl.unless_task_keywords and _keyword_hit(text, tmpl.unless_task_keywords):
                continue
            task_obj = next(
                (t for t in normalized.normalized_tasks if t.id == task_id),
                None,
            )
            if task_obj:
                matched_ids = {s.id for s in match_supplements_for_task(task_obj, document)}
                if tmpl.unless_supplement_ids and matched_ids.intersection(tmpl.unless_supplement_ids):
                    continue
            seen.add(key)
            open_items.append((tmpl, task_id))

    for task in build_plan.enabled_tasks():
        _check_task(task.id, _task_search_text(task))
    for task in normalized.normalized_tasks:
        _check_task(task.id, _task_search_text(task))
    return open_items


def run_interactive_clarifications(
    open_items: list[tuple[ClarificationTemplate, str]],
    *,
    input_fn=input,
) -> list[dict[str, Any]]:
    """終端互動澄清；回傳每筆 {template_id, task_id, question, answer}。"""
    if not open_items:
        return []
    print("\n--- Plan Normalize：需進一步確認 ---")
    answers: list[dict[str, Any]] = []
    for tmpl, task_id in open_items:
        print(f"\n任務 [{task_id}]")
        print(tmpl.question)
        reply = input_fn("> ").strip()
        if not reply:
            print("（略過，未提供回答）")
            continue
        answers.append(
            {
                "template_id": tmpl.id,
                "task_id": task_id,
                "question": tmpl.question,
                "answer": reply,
            }
        )
    return answers


def _slugify(text: str, *, max_len: int = 32) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (slug[:max_len] or "clarification")


def append_clarification_as_supplement(
    document: PromptSupplementsDocument,
    *,
    task_id: str,
    answer: str,
    match_keywords: list[str] | None = None,
) -> PromptSupplement:
    """將人類澄清寫入 document（可持久化至 JSON）。"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    sup_id = f"user_{_slugify(task_id)}_{ts}"
    suffix = 1
    existing_ids = {s.id for s in document.supplements}
    while sup_id in existing_ids:
        suffix += 1
        sup_id = f"user_{_slugify(task_id)}_{ts}_{suffix}"

    supplement = PromptSupplement(
        id=sup_id,
        description=f"Plan 互動澄清（任務 {task_id}）",
        match_keywords=match_keywords or [task_id],
        match_task_id_substrings=[task_id],
        prompt_block=answer.strip(),
        source="plan_interactive",
    )
    document.supplements.append(supplement)
    return supplement


def apply_clarification_answers(
    normalized: NormalizedPlan,
    answers: list[dict[str, Any]],
    document: PromptSupplementsDocument,
    *,
    persist: bool = True,
    supplements_path: Path | str | None = None,
) -> list[str]:
    """將澄清答案轉為 supplement 注入並可選寫回 JSON。"""
    injected: list[str] = []
    for item in answers:
        task_id = str(item["task_id"])
        answer = str(item["answer"])
        sup = append_clarification_as_supplement(
            document,
            task_id=task_id,
            answer=answer,
            match_keywords=[task_id],
        )
        injected.append(sup.id)
        for task in normalized.normalized_tasks:
            if task.id == task_id:
                inject_supplement_into_task(task, sup)
                break
    if persist and injected:
        save_prompt_supplements(document, supplements_path)
    return injected


def enrich_normalized_plan(
    build_plan: BuildPlan,
    normalized: NormalizedPlan,
    *,
    supplements_path: Path | str | None = None,
    plan_interactive: bool = False,
    input_fn=input,
) -> NormalizedPlan:
    """
    規劃後處理：注入 JSON 補充 prompt；可選互動澄清並寫回 JSON。
    """
    document = load_prompt_supplements(supplements_path)
    injected = apply_prompt_supplements(normalized, document)
    notes: list[str] = []
    if injected:
        notes.append(f"已注入 supplement: {', '.join(dict.fromkeys(injected))}")

    if plan_interactive:
        open_items = find_open_clarifications(build_plan, normalized, document)
        answers = run_interactive_clarifications(open_items, input_fn=input_fn)
        if answers:
            user_injected = apply_clarification_answers(
                normalized,
                answers,
                document,
                persist=True,
                supplements_path=supplements_path,
            )
            if user_injected:
                notes.append(f"互動澄清 supplement: {', '.join(user_injected)}")

    if notes:
        suffix = "；".join(notes)
        if normalized.plan_changelog:
            normalized.plan_changelog = f"{normalized.plan_changelog}；{suffix}"
        else:
            normalized.plan_changelog = suffix

    from core.pipeline.verify_hints import apply_verify_hints_to_normalized_tasks

    apply_verify_hints_to_normalized_tasks(normalized.normalized_tasks)
    return normalized
