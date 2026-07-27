"""Loads and runs small self-hosted models for the offline AI assistant
mode -- no OpenAI, no network call at answer time. Model weights are
fetched from Hugging Face the first time they're needed (typically during
an administrator's "Переобучить" click, see apps.assistant.training) and
cached on disk under LOCAL_AI_MODEL_CACHE_DIR from then on.

Loading is lazy and memoized per-process: nothing here touches torch or
downloads anything at import time, so importing this module (and therefore
apps.assistant.services) never requires the ML stack to actually work --
only calling embed_texts/generate_answer does. Tests replace these two
functions entirely, so the real models are never loaded during the suite.
"""

from __future__ import annotations

import threading

import numpy as np
from django.conf import settings

_embedding_model = None
_generation_tokenizer = None
_generation_model = None
_lock = threading.Lock()

_SYSTEM_PROMPT = (
    "Ты — ассистент корпоративной базы знаний. Используй ТОЛЬКО "
    "приведённые ниже фрагменты статей, чтобы своими словами ответить на "
    "вопрос. Если информации в них недостаточно, честно скажи об этом — "
    "не придумывай факты. Отвечай кратко и по делу, на русском языке."
)


def _cache_dir() -> str | None:
    return settings.LOCAL_AI_MODEL_CACHE_DIR or None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        with _lock:
            if _embedding_model is None:
                from sentence_transformers import SentenceTransformer

                _embedding_model = SentenceTransformer(
                    settings.LOCAL_AI_EMBEDDING_MODEL, cache_folder=_cache_dir()
                )
    return _embedding_model


def embed_texts(texts: list[str]) -> np.ndarray:
    """Returns an (N, D) float32 array of L2-normalized embeddings, so
    cosine similarity reduces to a plain dot product.
    """
    model = _get_embedding_model()
    embeddings = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    return np.asarray(embeddings, dtype=np.float32)


def _get_generation_model():
    global _generation_tokenizer, _generation_model
    if _generation_model is None:
        with _lock:
            if _generation_model is None:
                from transformers import AutoModelForCausalLM, AutoTokenizer

                model_name = settings.LOCAL_AI_GENERATION_MODEL
                _generation_tokenizer = AutoTokenizer.from_pretrained(
                    model_name, cache_dir=_cache_dir()
                )
                _generation_model = AutoModelForCausalLM.from_pretrained(
                    model_name, cache_dir=_cache_dir()
                )
    return _generation_tokenizer, _generation_model


def generate_answer(*, context: str, question: str, max_new_tokens: int = 300) -> str:
    """Generates a synthesized answer from retrieved article fragments,
    using a small local instruct model -- not an extract of the input.
    """
    import torch

    tokenizer, model = _get_generation_model()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Фрагменты статей:\n\n{context}\n\n---\n\nВопрос: {question}",
        },
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt")

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )

    generated = output_ids[0][inputs["input_ids"].shape[1] :]
    return tokenizer.decode(generated, skip_special_tokens=True).strip()
