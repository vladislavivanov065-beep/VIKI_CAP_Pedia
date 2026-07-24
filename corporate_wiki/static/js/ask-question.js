(function () {
    "use strict";

    function escapeHtml(text) {
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    document.querySelectorAll("[data-ask-question-form]").forEach(function (form) {
        var container = form.closest(".rail-block") || form.parentElement;
        var submitButton = form.querySelector("[data-ask-question-submit]");
        var resultBox = container.querySelector("[data-ask-question-result]");
        var answerEl = container.querySelector("[data-ask-question-answer]");
        var sourcesEl = container.querySelector("[data-ask-question-sources]");
        var note = container.querySelector("[data-ask-question-note]");
        var url = form.getAttribute("data-ask-question-url");
        var csrfInput = form.querySelector('input[name="csrfmiddlewaretoken"]');

        function showNote(text) {
            if (!note) {
                return;
            }
            note.textContent = text;
            note.hidden = !text;
        }

        function renderResult(data) {
            if (!resultBox || !answerEl) {
                return;
            }
            answerEl.textContent = data.answer;
            if (sourcesEl) {
                if (data.sources && data.sources.length) {
                    sourcesEl.innerHTML = data.sources
                        .map(function (source) {
                            var url = "/articles/" + encodeURIComponent(source.slug) + "/";
                            return (
                                '<li><a href="' + url + '">' + escapeHtml(source.title) + "</a></li>"
                            );
                        })
                        .join("");
                } else {
                    sourcesEl.innerHTML = "";
                }
            }
            resultBox.hidden = false;
        }

        form.addEventListener("submit", function (event) {
            event.preventDefault();
            var question = form.querySelector("textarea[name='question']").value.trim();
            if (!question || !url) {
                return;
            }

            showNote("");
            if (resultBox) {
                resultBox.hidden = true;
            }
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = "Спрашиваю…";
            }

            fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfInput ? csrfInput.value : "",
                },
                body: JSON.stringify({ question: question }),
            })
                .then(function (response) {
                    return response.json().then(function (data) {
                        return { ok: response.ok, data: data };
                    });
                })
                .then(function (result) {
                    if (!result.ok) {
                        showNote(result.data.error || "Не удалось получить ответ.");
                        return;
                    }
                    renderResult(result.data);
                })
                .catch(function () {
                    showNote("Не удалось связаться с сервером. Попробуйте ещё раз.");
                })
                .finally(function () {
                    if (submitButton) {
                        submitButton.disabled = false;
                        submitButton.textContent = "Спросить";
                    }
                });
        });
    });
})();
