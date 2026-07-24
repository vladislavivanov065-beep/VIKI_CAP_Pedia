(function () {
    "use strict";

    document.querySelectorAll("[data-ask-question-form]").forEach(function (form) {
        var container = form.closest(".rail-block") || form.parentElement;
        var submitButton = form.querySelector("[data-ask-question-submit]");
        var resultBox = container.querySelector("[data-ask-question-result]");
        var answerEl = container.querySelector("[data-ask-question-answer]");
        var note = container.querySelector("[data-ask-question-note]");
        var url = form.getAttribute("data-ask-question-url");
        var articleSlug = form.getAttribute("data-article-slug");
        var csrfInput = form.querySelector('input[name="csrfmiddlewaretoken"]');

        function showNote(text) {
            if (!note) {
                return;
            }
            note.textContent = text;
            note.hidden = !text;
        }

        function renderAnswer(answer) {
            if (!resultBox || !answerEl) {
                return;
            }
            answerEl.textContent = answer;
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
                body: JSON.stringify({ question: question, article_slug: articleSlug }),
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
                    renderAnswer(result.data.answer);
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
