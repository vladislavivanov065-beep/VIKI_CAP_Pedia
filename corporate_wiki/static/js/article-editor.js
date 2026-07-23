(function () {
    "use strict";

    function getCsrfToken() {
        var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return input ? input.value : "";
    }

    function insertAtCursor(textarea, text) {
        var start = textarea.selectionStart || 0;
        var end = textarea.selectionEnd || 0;
        var before = textarea.value.slice(0, start);
        var after = textarea.value.slice(end);
        textarea.value = before + text + after;
        var pos = start + text.length;
        textarea.selectionStart = textarea.selectionEnd = pos;
        textarea.focus();
    }

    function uploadImage(file, textarea) {
        var formData = new FormData();
        formData.append("file", file);

        fetch("/images/upload/", {
            method: "POST",
            headers: { "X-CSRFToken": getCsrfToken() },
            body: formData,
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                if (result.ok) {
                    insertAtCursor(textarea, result.data.markdown + "\n");
                } else {
                    window.alert(result.data.error || "Не удалось загрузить изображение.");
                }
            })
            .catch(function () {
                window.alert("Не удалось загрузить изображение.");
            });
    }

    function wirePreview(form, textarea) {
        var previewButton = form.querySelector("[data-preview-target]");
        if (!previewButton) {
            return;
        }
        previewButton.addEventListener("click", function () {
            var target = document.getElementById(previewButton.getAttribute("data-preview-target"));
            if (!target) {
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
    }

    function wireImageUpload(form, textarea) {
        var uploadButton = form.querySelector("[data-image-upload]");
        var fileInput = form.querySelector("[data-image-input]");
        if (uploadButton && fileInput) {
            uploadButton.addEventListener("click", function () {
                fileInput.click();
            });
            fileInput.addEventListener("change", function () {
                if (fileInput.files && fileInput.files[0]) {
                    uploadImage(fileInput.files[0], textarea);
                    fileInput.value = "";
                }
            });
        }

        textarea.addEventListener("dragover", function (event) {
            event.preventDefault();
        });
        textarea.addEventListener("drop", function (event) {
            event.preventDefault();
            var file = event.dataTransfer && event.dataTransfer.files[0];
            if (file) {
                uploadImage(file, textarea);
            }
        });
    }

    document.querySelectorAll("form.article-form").forEach(function (form) {
        var textarea = form.querySelector("textarea[name='content_source']");
        if (!textarea) {
            return;
        }
        wirePreview(form, textarea);
        wireImageUpload(form, textarea);
    });
})();
