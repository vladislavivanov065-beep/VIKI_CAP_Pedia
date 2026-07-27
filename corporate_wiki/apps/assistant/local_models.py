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
    "Ты — ассистент корпоративной базы знаний. Тебе даны фрагменты статей и "
    "вопрос. Отвечай СТРОГО и ТОЛЬКО на основе слов и фактов из фрагментов "
    "ниже — не добавляй ничего, чего там нет, не придумывай примеры, цифры "
    "или ситуации. Если фрагменты действительно не содержат ответа, ответь "
    "ровно одной фразой: «В статьях нет ответа на этот вопрос.» Если ответ "
    "есть — перескажи его своими словами, коротко (1-2 предложения), на "
    "русском языке."
)

# intfloat/multilingual-e5-* models are trained on asymmetric "query: "/
# "passage: " prefixes and lose retrieval quality without them; other
# embedding models are used as-is.
_E5_QUERY_PREFIX = "query: "
_E5_PASSAGE_PREFIX = "passage: "


def _cache_dir() -> str | None:
    return settings.LOCAL_AI_MODEL_CACHE_DIR or None


def _is_e5_model() -> bool:
    return "e5" in settings.LOCAL_AI_EMBEDDING_MODEL.lower()


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


def embed_texts(texts: list[str], *, is_query: bool = False) -> np.ndarray:
    """Returns an (N, D) float32 array of L2-normalized embeddings, so
    cosine similarity reduces to a plain dot product.

    is_query distinguishes a question (searching *for* a passage) from a
    passage/chunk being indexed -- irrelevant for most embedding models,
    but required for good results from the e5 family (see _is_e5_model).
    """
    if _is_e5_model():
        prefix = _E5_QUERY_PREFIX if is_query else _E5_PASSAGE_PREFIX
        texts = [prefix + text for text in texts]
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


def generate_answer(*, context: str, question: str, max_new_tokens: int = 150) -> str:
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
