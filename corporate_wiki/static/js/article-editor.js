(function () {
    "use strict";

    var previewButton = document.querySelector("[data-preview-target]");
    if (!previewButton) {
        return;
    }

    function getCsrfToken() {
        var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return input ? input.value : "";
    }

    previewButton.addEventListener("click", function () {
        var form = previewButton.closest("form");
        var textarea = form.querySelector("textarea[name='content_source']");
        var target = document.getElementById(previewButton.getAttribute("data-preview-target"));
        if (!textarea || !target) {
            return;
        }

        var body = new URLSearchParams();
        body.set("content_source", textarea.value);

        fetch("/articles/preview/", {
            method: "POST",
            headers: {
                "X-CSRFToken": getCsrfToken(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: body.toString(),
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                target.innerHTML = data.content_html || "<p>Нет содержимого.</p>";
            })
            .catch(function () {
                target.innerHTML = "<p>Не удалось загрузить предпросмотр.</p>";
            });
    });
})();
