(function () {
    "use strict";

    document.querySelectorAll("[data-ask-question-form]").forEach(function (form) {
        var container = form.closest(".rail-block") || form.parentElement;
        var submitButton = form.querySelector("[data-ask-question-submit]");
        var resultBox = container.querySelector("[data-ask-question-result]");
        var answerEl = container.querySelector("[data-ask-question-answer]");
        var alternativesBox = container.querySelector("[data-ask-question-alternatives]");
        var alternativesList = container.querySelector("[data-ask-question-alternatives-list]");
        var note = container.querySelector("[data-ask-question-note]");
        var url = form.getAttribute("data-ask-question-url");
        var articleSlug = form.getAttribute("data-article-slug");
        var csrfInput = form.querySelector('input[name="csrfmiddlewaretoken"]');
        var consentCheckbox = form.querySelector("[data-ask-question-consent]");

        function showNote(text) {
            if (!note) {
                return;
            }
            note.textContent = text;
            note.hidden = !text;
        }

        function renderAnswer(answer, alternatives) {
            if (!resultBox || !answerEl) {
                return;
            }
            answerEl.textContent = answer;

            if (alternativesBox && alternativesList) {
                alternativesList.innerHTML = "";
                var items = alternatives || [];
                items.forEach(function (alternative) {
                    var li = document.createElement("li");
                    li.textContent = alternative;
                    alternativesList.appendChild(li);
                });
                alternativesBox.hidden = items.length === 0;
            }

            resultBox.hidden = false;
        }

        form.addEventListener("submit", function (event) {
            event.preventDefault();
            var question = form.querySelector("textarea[name='question']").value.trim();
            if (!question || !url) {
                return;
            }

            // A disabled checkbox means the admin turned ChatGPT off site-wide --
            // that only rules out the ChatGPT path, the local search still runs.
            var useChatGPT = !!(consentCheckbox && !consentCheckbox.disabled && consentCheckbox.checked);

            if (consentCheckbox && consentCheckbox.disabled) {
                showNote("Запросы к ChatGPT отключены администратором. Ищу ответ в тексте статьи…");
            } else {
                showNote(useChatGPT ? "Спрашиваю у ChatGPT…" : "Ищу ответ в тексте статьи…");
            }
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
                body: JSON.stringify({
                    question: question,
                    article_slug: articleSlug,
                    use_chatgpt: useChatGPT,
                }),
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
                    showNote("");
                    renderAnswer(result.data.answer, result.data.alternatives);
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
