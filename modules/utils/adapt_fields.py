
from pathlib import Path
from typing import Any
import re
from statistics import mean
from deepeval.test_case import LLMTestCase


# Max page distance considered for partial credit when comparing expected vs actual references.
PAGE_TOLERANCE = 3


def _reference_to_text(ref: Any) -> str:
    """Render references (dict or string) into a compact text block."""
    if isinstance(ref, str):
        return ref.strip()

    if not isinstance(ref, dict):
        return str(ref)

    source_file = (
        ref.get("source_file")
        or ref.get("documento")
        or ref.get("source")
        or "unknown_document"
    )
    page = ref.get("page_number") or ref.get("pagina") or "?"
    section = ref.get("section_name") or ref.get("seccion") or ""
    content = ref.get("content") or ref.get("text") or ref.get("texto") or ""

    header = f"source_file={source_file}; page={page}; section={section}".strip()
    return f"{header}\ncontent={content}".strip()


def _to_int_or_none(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        m = re.search(r"\d+", value)
        return int(m.group(0)) if m else None
    return None


def _normalize_expected_reference(ref: Any) -> dict[str, Any]:
    """
    Normalize expected references from either:
    - string: "SomeFile.pdf, page 7"
    - dict with keys in Spanish/English
    """
    if isinstance(ref, dict):
        doc = (
            ref.get("source_file")
            or ref.get("documento")
            or ref.get("source")
            or ""
        )
        page = _to_int_or_none(ref.get("page_number") or ref.get("pagina") or ref.get("page"))
        return {"documento": str(doc).strip(), "pagina": page, "raw": ref}

    if isinstance(ref, str):
        # Pattern examples:
        # - "United-States_Results-Report_2022–2024.pdf, page 7"
        # - "United-States_Results-Report_2022–2024.pdf, pagina 7"
        m = re.match(r"^\s*(.*?)\s*(?:,\s*(?:page|pagina)\s*(\d+))?\s*$", ref, flags=re.IGNORECASE)
        if m:
            doc = (m.group(1) or "").strip()
            page = int(m.group(2)) if m.group(2) else None
            return {"documento": doc, "pagina": page, "raw": ref}
        return {"documento": ref.strip(), "pagina": None, "raw": ref}

    return {"documento": str(ref), "pagina": None, "raw": ref}


def _normalize_actual_reference(ref: Any) -> dict[str, Any]:
    if not isinstance(ref, dict):
        return {"documento": str(ref), "pagina": None, "raw": ref}

    doc = (
        ref.get("documento")
        or ref.get("source_file")
        or ref.get("source")
        or ""
    )
    page = _to_int_or_none(ref.get("pagina") or ref.get("page_number") or ref.get("page"))
    return {"documento": str(doc).strip(), "pagina": page, "raw": ref}


def compute_page_similarity(expected_refs: list[Any], actual_refs: list[Any], tolerance: int = PAGE_TOLERANCE) -> dict[str, Any]:
    """
    Score page similarity in [0, 1] using closest page distance per expected reference.
    - 1.0 for exact page match
    - linearly decays until 0 when distance > tolerance
    Also prefers matching within the same document when possible.
    """
    exp_norm = [_normalize_expected_reference(r) for r in expected_refs]
    act_norm = [_normalize_actual_reference(r) for r in actual_refs]

    scored_items = []
    for exp in exp_norm:
        exp_doc = (exp.get("documento") or "").lower()
        exp_page = exp.get("pagina")

        if exp_page is None:
            continue

        same_doc_candidates = [a for a in act_norm if (a.get("documento") or "").lower() == exp_doc and a.get("pagina") is not None]
        page_candidates = same_doc_candidates or [a for a in act_norm if a.get("pagina") is not None]

        if not page_candidates:
            scored_items.append(
                {
                    "expected_documento": exp.get("documento"),
                    "expected_pagina": exp_page,
                    "matched_documento": None,
                    "matched_pagina": None,
                    "distance": None,
                    "score": 0.0,
                }
            )
            continue

        best = min(page_candidates, key=lambda a: abs(int(a["pagina"]) - int(exp_page)))
        distance = abs(int(best["pagina"]) - int(exp_page))
        raw_score = 1 - (distance / max(1, tolerance))
        score = max(0.0, min(1.0, raw_score))

        scored_items.append(
            {
                "expected_documento": exp.get("documento"),
                "expected_pagina": exp_page,
                "matched_documento": best.get("documento"),
                "matched_pagina": best.get("pagina"),
                "distance": distance,
                "score": score,
            }
        )

    avg_score = mean([x["score"] for x in scored_items]) if scored_items else None
    return {
        "avg_page_similarity": avg_score,
        "details": scored_items,
    }


def build_testcase_from_output_row(row: dict[str, Any]) -> LLMTestCase:
    question = row.get("question", "")
    expected_output = row.get("expected_output") or row.get("expected_answer", "")
    actual_output = row.get("actual_output", "")

    expected_refs = row.get("expected_references", [])
    actual_refs = row.get("actual_references", [])

    # retrieval_context is what model used as evidence (actual references)
    retrieval_context = [_reference_to_text(r) for r in actual_refs]

    # Include expected reference text in expected output for content+citation aware judgement
    expected_refs_text = "\n".join(_reference_to_text(r) for r in expected_refs)
    combined_expected_output = (
        expected_output
        if not expected_refs_text
        else f"{expected_output}\n\nExpected references:\n{expected_refs_text}"
    )

    return LLMTestCase(
        input=question,
        actual_output=actual_output,
        expected_output=combined_expected_output,
        retrieval_context=retrieval_context,
    )