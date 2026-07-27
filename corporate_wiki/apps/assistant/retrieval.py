"""Corpus-wide retrieval over the embeddings built by
apps.assistant.training.retrain_local_model -- ranks stored article chunks
by similarity to a question. Embeddings are stored L2-normalized (see
apps.assistant.local_models.embed_texts), so cosine similarity reduces to
a plain dot product.
"""

from __future__ import annotations

import numpy as np

from apps.assistant import local_models
from apps.assistant.models import ArticleChunkEmbedding

# Below this similarity, a chunk is treated as unrelated rather than fed
# to the generator as context -- keeps an off-topic question from being
# "answered" out of whatever chunk happened to rank highest regardless.
_MIN_SIMILARITY = 0.2


def find_relevant_chunks(*, question: str, top_k: int = 5) -> list[ArticleChunkEmbedding]:
    chunks = list(
        ArticleChunkEmbedding.objects.filter(article__is_archived=False).select_related("article")
    )
    if not chunks:
        return []

    matrix = np.stack([np.frombuffer(chunk.embedding, dtype=np.float32) for chunk in chunks])
    (query_embedding,) = local_models.embed_texts([question])
    similarities = matrix @ query_embedding

    ranked_indices = np.argsort(-similarities)
    results = []
    for index in ranked_indices[:top_k]:
        if similarities[index] < _MIN_SIMILARITY:
            break
        results.append(chunks[index])
    return results
