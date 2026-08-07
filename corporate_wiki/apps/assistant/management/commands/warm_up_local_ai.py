"""Loads the local AI's embedding and cross-encoder models into memory once,
at deploy/restart time (see entrypoint.sh) -- so the cost of reading
weights off disk and initializing torch lands there, not on whichever
user happens to ask the first question against a fresh process. Both
models are memoized per-process after their first real use (see
apps.assistant.local_models), so this only ever pays that cost once per
process, same as a real question would -- it just moves *when* it's paid.

No-op if local AI has never been trained (see apps.assistant.training):
an install that doesn't use this feature shouldn't load models it will
never call, same guard as apps.assistant.training.
start_sync_article_embeddings_in_background.
"""

from django.core.management.base import BaseCommand

from apps.assistant import local_models
from apps.assistant.models import AssistantSettings


class Command(BaseCommand):
    help = (
        "Preload the local AI's embedding and cross-encoder models into "
        "memory so the first real question doesn't have to. No-op until "
        "an administrator has trained the local AI at least once."
    )

    def handle(self, *args, **options):
        if not AssistantSettings.get_solo().local_ai_trained_at:
            self.stdout.write("Локальный ИИ ещё не обучен, пропускаю прогрев моделей.")
            return

        try:
            self.stdout.write("Загружаю модель эмбеддингов…")
            local_models.embed_texts(["прогрев"], is_query=True)
            self.stdout.write("Загружаю модель кросс-энкодера…")
            local_models.score_pairs(question="прогрев", candidates=["прогрев"])
        except Exception as exc:
            # Not fatal -- degrades to the same lazy-load-on-first-question
            # behavior this command exists to avoid, rather than failing
            # the whole deploy over a model that's still reachable most of
            # the time (e.g. a transient network hiccup fetching weights).
            self.stdout.write(
                self.style.WARNING(
                    f"Не удалось прогреть модели локального ИИ ({exc}) — "
                    "первый вопрос после старта загрузит их сам."
                )
            )
            return

        self.stdout.write(self.style.SUCCESS("Модели локального ИИ загружены."))
