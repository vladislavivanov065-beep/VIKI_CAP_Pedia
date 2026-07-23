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

    function uploadImage(file, altText, caption, textarea, onDone) {
        var formData = new FormData();
        formData.append("file", file);
        formData.append("alt_text", altText || "");
        formData.append("caption", caption || "");

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
                    var snippet = caption
                        ? "![[image:" + result.data.id + "|" + caption + "]]"
                        : result.data.markdown;
                    insertAtCursor(textarea, snippet + "\n");
                } else {
                    window.alert(result.data.error || "Не удалось загрузить изображение.");
                }
            })
            .catch(function () {
                window.alert("Не удалось загрузить изображение.");
            })
            .then(onDone);
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

    function guessAltFromFilename(filename) {
        return (filename || "").replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
    }

    function wireImageUpload(form, textarea) {
        var uploadButton = form.querySelector("[data-image-upload]");
        var fileInput = form.querySelector("[data-image-input]");
        var panel = form.querySelector("[data-image-panel]");
        if (!panel) {
            return;
        }
        var filenameLabel = panel.querySelector("[data-image-filename]");
        var altInput = panel.querySelector("[data-image-alt]");
        var captionInput = panel.querySelector("[data-image-caption]");
        var confirmButton = panel.querySelector("[data-image-confirm]");
        var cancelButton = panel.querySelector("[data-image-cancel]");
        var pendingFile = null;

        function openPanel(file) {
            pendingFile = file;
            filenameLabel.textContent = file.name;
            altInput.value = guessAltFromFilename(file.name);
            captionInput.value = "";
            panel.hidden = false;
            altInput.focus();
        }

        function closePanel() {
            pendingFile = null;
            panel.hidden = true;
            if (fileInput) {
                fileInput.value = "";
            }
        }

        if (uploadButton && fileInput) {
            uploadButton.addEventListener("click", function () {
                fileInput.click();
            });
            fileInput.addEventListener("change", function () {
                if (fileInput.files && fileInput.files[0]) {
                    openPanel(fileInput.files[0]);
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
                openPanel(file);
            }
        });

        if (confirmButton) {
            confirmButton.addEventListener("click", function () {
                if (!pendingFile) {
                    return;
                }
                if (!altInput.value.trim()) {
                    altInput.focus();
                    altInput.setCustomValidity("Укажите альтернативный текст для изображения.");
                    altInput.reportValidity();
                    return;
                }
                altInput.setCustomValidity("");
                var file = pendingFile;
                confirmButton.disabled = true;
                uploadImage(file, altInput.value.trim(), captionInput.value.trim(), textarea, function () {
                    confirmButton.disabled = false;
                    closePanel();
                });
            });
        }

        if (cancelButton) {
            cancelButton.addEventListener("click", closePanel);
        }
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
