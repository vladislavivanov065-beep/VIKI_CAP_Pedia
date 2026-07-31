"""Loads and runs the local embedding and cross-encoder models for the
offline AI assistant mode -- no OpenAI, no network call at answer time.
Model weights are fetched from Hugging Face the first time they're needed
(typically during an administrator's "Переобучить" click, see
apps.assistant.training, or the first question that needs reranking, see
apps.assistant.local_ai) and cached on disk under LOCAL_AI_MODEL_CACHE_DIR
from then on.

Loading is lazy and memoized per-process: nothing here touches torch or
downloads anything at import time, so importing this module (and therefore
apps.assistant.services) never requires the ML stack to actually work --
only calling embed_texts/score_pairs does. Tests replace those functions
entirely, so the real models are never loaded during the suite.
"""

from __future__ import annotations

import threading

import numpy as np
from django.conf import settings

_embedding_model = None
_embedding_lock = threading.Lock()
_cross_encoder_model = None
_cross_encoder_lock = threading.Lock()

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
        with _embedding_lock:
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


def _get_cross_encoder_model():
    global _cross_encoder_model
    if _cross_encoder_model is None:
        with _cross_encoder_lock:
            if _cross_encoder_model is None:
                from sentence_transformers import CrossEncoder

                _cross_encoder_model = CrossEncoder(
                    settings.LOCAL_AI_CROSS_ENCODER_MODEL, cache_folder=_cache_dir()
                )
    return _cross_encoder_model


def score_pairs(*, question: str, candidates: list[str]) -> list[float]:
    """Relevance score in [0, 1] for each (question, candidate) pair, from
    a cross-encoder that looks at both texts together in one forward pass
    -- unlike cosine similarity between separately computed embeddings,
    it can weigh how the words in the two texts relate to *each other*,
    so it's a better judge of "does this actually answer the question"
    than embedding similarity or keyword overlap alone. Only ever called
    on an already-small candidate pool (see apps.assistant.local_ai) --
    too slow to run over a whole corpus the way embed_texts is.
    """
    model = _get_cross_encoder_model()
    pairs = [(question, candidate) for candidate in candidates]
    scores = model.predict(pairs, convert_to_numpy=True)
    return [float(score) for score in scores]
