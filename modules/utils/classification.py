from __future__ import annotations

from pathlib import Path
from typing import Any


def get_available_categories(pdf_root: Path) -> list[str]:
    """
    Dynamically discover available categories from PDF folder structure.
    Categories are top-level folder names under pdf_root, excluding hidden dirs.
    """
    if not pdf_root.exists():
        return []

    return sorted(
        d.name
        for d in pdf_root.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


def classify_category_with_llm(
    question: str,
    available_categories: list[str],
    llm: Any,
    confidence_threshold: float = 0.6,
) -> tuple[str | None, float]:
    """
    Classify a question into one of the available categories using LLM zero-shot
    classification.

    The LLM is asked to reply in ``CATEGORIA|CONFIANZA`` format so the result
    can be parsed deterministically.  If the LLM output cannot be parsed or the
    predicted category is not in the allowed list the function degrades
    gracefully and returns ``(None, score)``.

    Args:
        question:              User question text.
        available_categories:  Valid category names (usually discovered with
                               ``get_available_categories``).
        llm:                   LangChain chat-model instance (must expose
                               ``.invoke()``).
        confidence_threshold:  Minimum confidence score [0-1] required to
                               return a prediction.  Predictions below this
                               threshold return ``(None, score)``.

    Returns:
        A tuple ``(predicted_category, confidence_score)``.  Returns
        ``(None, score)`` when confidence is too low or classification fails.
    """
    if not available_categories:
        return None, 0.0

    categories_str = ", ".join(available_categories)
    prompt = (
        f"Clasifica la siguiente pregunta en UNA de estas categorías: {categories_str}\n\n"
        f'Pregunta: "{question}"\n\n'
        "Responde SOLO con:\n"
        "1. El nombre exacto de la categoría (tal como aparece en la lista)\n"
        "2. Un número de confianza entre 0 y 1 (ej: 0.95)\n\n"
        "Formato: CATEGORIA|CONFIANZA\n"
        "Ejemplo: legal|0.92"
    )

    try:
        response = llm.invoke(prompt)
        response_text = (
            response.content.strip()
            if hasattr(response, "content")
            else str(response).strip()
        )

        # --- Parse structured response -----------------------------------------
        if "|" in response_text:
            parts = response_text.split("|", maxsplit=1)
            predicted_cat = parts[0].strip()
            try:
                confidence = float(parts[1].strip())
            except ValueError:
                confidence = 0.5
        else:
            # Fallback: look for any known category name inside the free text
            predicted_cat = None
            confidence = 0.0
            for cat in available_categories:
                if cat.lower() in response_text.lower():
                    predicted_cat = cat
                    confidence = 0.5
                    break

        # --- Validate and clamp ------------------------------------------------
        if predicted_cat not in available_categories:
            return None, max(0.0, min(1.0, confidence - 0.3))

        confidence = max(0.0, min(1.0, confidence))

        if confidence < confidence_threshold:
            return None, confidence

        return predicted_cat, confidence

    except Exception as exc:  # noqa: BLE001
        print(f"[classification] Error during LLM classification: {exc}")
        return None, 0.0
