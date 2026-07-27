(function () {
    "use strict";

    var root = document.querySelector("[data-local-ai-root]");
    if (!root) {
        return;
    }

    var statusUrl = root.getAttribute("data-status-url");
    var logEl = root.querySelector("[data-local-ai-log]");
    var statusEl = root.querySelector("[data-local-ai-status]");
    var errorEl = root.querySelector("[data-local-ai-error]");
    var retrainBtn = root.querySelector("[data-local-ai-retrain-btn]");
    var pollTimer = null;

    function formatStatus(data) {
        if (data.is_training) {
            return "Обучение выполняется…";
        }
        if (data.trained_at) {
            var trainedAt = new Date(data.trained_at).toLocaleString("ru-RU");
            var by = data.trained_by ? " (" + data.trained_by + ")" : "";
            return (
                "Обучен: " + trainedAt + by + ". Статей: " + data.article_count +
                ", фрагментов: " + data.chunk_count + "."
            );
        }
        return "Ещё не обучен — ответы даются простым поиском по тексту статьи.";
    }

    function render(data) {
        if (logEl) {
            logEl.textContent = data.log || "";
            logEl.scrollTop = logEl.scrollHeight;
        }
        if (statusEl) {
            statusEl.textContent = formatStatus(data);
        }
        if (errorEl) {
            if (data.last_error) {
                errorEl.textContent = "Последняя ошибка обучения: " + data.last_error;
                errorEl.hidden = false;
            } else {
                errorEl.hidden = true;
            }
        }
        if (retrainBtn) {
            retrainBtn.disabled = data.is_training;
        }
        if (data.is_training) {
            scheduleNextPoll();
        }
    }

    function poll() {
        fetch(statusUrl)
            .then(function (response) {
                return response.json();
            })
            .then(render)
            .catch(function () {
                scheduleNextPoll();
            });
    }

    function scheduleNextPoll() {
        window.clearTimeout(pollTimer);
        pollTimer = window.setTimeout(poll, 1500);
    }

    if (root.getAttribute("data-training") === "true") {
        poll();
    }
})();
