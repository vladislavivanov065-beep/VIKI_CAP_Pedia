"""Loads and runs the local embedding model for the offline AI assistant
mode -- no OpenAI, no network call at answer time. Model weights are
fetched from Hugging Face the first time they're needed (typically during
an administrator's "Переобучить" click, see apps.assistant.training) and
cached on disk under LOCAL_AI_MODEL_CACHE_DIR from then on.

Loading is lazy and memoized per-process: nothing here touches torch or
downloads anything at import time, so importing this module (and therefore
apps.assistant.services) never requires the ML stack to actually work --
only calling embed_texts does. Tests replace that function entirely, so
the real model is never loaded during the suite.
"""

from __future__ import annotations

import threading

import numpy as np
from django.conf import settings

_embedding_model = None
_lock = threading.Lock()

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
