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

    // Mirror the CSS properties that affect text layout/wrapping, so a
    // hidden mirror <div> reproduces the textarea's line breaks exactly.
    // This is the standard "textarea caret position" technique: since we
    // can't ask a plain <textarea> where a substring is rendered, we
    // render the same text in a same-sized/same-font hidden element and
    // read the pixel position of a marker span placed inside it.
    var MIRRORED_STYLE_PROPERTIES = [
        "direction", "boxSizing", "width", "height", "overflowX", "overflowY",
        "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth", "borderStyle",
        "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
        "fontStyle", "fontVariant", "fontWeight", "fontStretch", "fontSize", "lineHeight", "fontFamily",
        "textAlign", "textTransform", "textIndent", "letterSpacing", "wordSpacing", "tabSize",
    ];

    function escapeHtml(text) {
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function escapeRegExp(text) {
        return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    // Ranges of the source text that are already markup, not plain prose:
    // fenced code blocks, inline code, and existing [[...]]/![[...]] links.
    // Matches are never suggested inside these.
    function findExcludedRanges(text) {
        var ranges = [];
        var patterns = [/```[\s\S]*?```/g, /`[^`\n]*`/g, /!?\[\[[^\]]*\]\]/g];
        patterns.forEach(function (pattern) {
            var match;
            while ((match = pattern.exec(text)) !== null) {
                ranges.push([match.index, match.index + match[0].length]);
            }
        });
        return ranges;
    }

    function overlapsAny(start, end, ranges) {
        for (var i = 0; i < ranges.length; i++) {
            if (start < ranges[i][1] && end > ranges[i][0]) {
                return true;
            }
        }
        return false;
    }

    var MAX_HINTS = 60;

    function findTitleMatches(text, articles) {
        if (!articles.length) {
            return [];
        }
        // Longest title first, so overlapping titles ("CardsPro" vs.
        // "CardsPro Mobile") prefer the longer/more specific match.
        var sorted = articles.slice().sort(function (a, b) {
            return b.title.length - a.title.length;
        });
        var alternation = sorted.map(function (a) {
            return escapeRegExp(a.title);
        }).join("|");
        var byLowerTitle = {};
        sorted.forEach(function (a) {
            byLowerTitle[a.title.toLowerCase()] = a;
        });

        var pattern;
        try {
            pattern = new RegExp(
                "(?<![\\p{L}\\p{N}_])(" + alternation + ")(?![\\p{L}\\p{N}_])", "giu"
            );
        } catch (err) {
            // Unicode property escapes unsupported (very old browser) —
            // degrade gracefully to no hints rather than throwing.
            return [];
        }

        var excluded = findExcludedRanges(text);
        var matches = [];
        var match;
        while ((match = pattern.exec(text)) !== null && matches.length < MAX_HINTS) {
            var start = match.index;
            var end = start + match[0].length;
            if (!overlapsAny(start, end, excluded)) {
                matches.push({
                    start: start,
                    end: end,
                    matchedText: match[0],
                    article: byLowerTitle[match[0].toLowerCase()],
                });
            }
        }
        return matches;
    }

    function wireWikiLinkHints(form, textarea) {
        var suggestionsUrl = form.getAttribute("data-link-suggestions-url");
        if (!suggestionsUrl) {
            return;
        }
        var excludeSlug = form.getAttribute("data-exclude-slug") || "";

        var host = document.createElement("div");
        host.className = "wikilink-hint-host";
        textarea.parentNode.insertBefore(host, textarea);
        host.appendChild(textarea);

        var mirror = document.createElement("div");
        mirror.className = "wikilink-hint-mirror";
        host.appendChild(mirror);

        var hintLayer = document.createElement("div");
        hintLayer.className = "wikilink-hint-layer";
        host.appendChild(hintLayer);

        var articles = [];
        var currentMatches = [];
        var pendingTimer = null;

        function syncMirrorStyle() {
            var computed = window.getComputedStyle(textarea);
            MIRRORED_STYLE_PROPERTIES.forEach(function (prop) {
                mirror.style[prop] = computed[prop];
            });
            mirror.style.width = textarea.offsetWidth + "px";
            mirror.style.height = textarea.offsetHeight + "px";
            mirror.style.whiteSpace = "pre-wrap";
            mirror.style.wordWrap = "break-word";
            mirror.style.overflowWrap = "break-word";
        }

        function renderHints() {
            hintLayer.innerHTML = "";
            if (!currentMatches.length) {
                return;
            }
            syncMirrorStyle();

            var text = textarea.value;
            var html = "";
            var cursor = 0;
            currentMatches.forEach(function (m, index) {
                html += escapeHtml(text.slice(cursor, m.start));
                html += '<span data-marker="' + index + '">' + escapeHtml(m.matchedText) + "</span>";
                cursor = m.end;
            });
            html += escapeHtml(text.slice(cursor));
            // A trailing newline needs a non-breaking placeholder or the
            // mirror collapses its final empty line, throwing off height.
            mirror.innerHTML = html + "​";
            mirror.scrollTop = textarea.scrollTop;
            mirror.scrollLeft = textarea.scrollLeft;

            var hostRect = host.getBoundingClientRect();
            currentMatches.forEach(function (m, index) {
                var marker = mirror.querySelector('span[data-marker="' + index + '"]');
                if (!marker) {
                    return;
                }
                var rect = marker.getBoundingClientRect();
                if (rect.bottom < hostRect.top || rect.top > hostRect.bottom) {
                    return; // scrolled out of view
                }
                var button = document.createElement("button");
                button.type = "button";
                button.className = "wikilink-hint";
                button.title = "Сделать ссылку на статью «" + m.article.title + "»";
                button.textContent = "🔗";
                button.style.left = (rect.right - hostRect.left) + "px";
                button.style.top = (rect.top - hostRect.top) + "px";
                button.addEventListener("click", function () {
                    convertMatch(m);
                });
                hintLayer.appendChild(button);
            });
        }

        function convertMatch(m) {
            var text = textarea.value;
            var isSameCase = m.matchedText.toLowerCase() === m.article.title.toLowerCase();
            var replacement = isSameCase
                ? "[[" + m.article.title + "]]"
                : "[[" + m.article.title + "|" + m.matchedText + "]]";
            textarea.value = text.slice(0, m.start) + replacement + text.slice(m.end);
            textarea.focus();
            textarea.selectionStart = textarea.selectionEnd = m.start + replacement.length;
            scheduleRematch(0);
        }

        function rematch() {
            currentMatches = findTitleMatches(textarea.value, articles);
            renderHints();
        }

        function scheduleRematch(delay) {
            if (pendingTimer) {
                window.clearTimeout(pendingTimer);
            }
            pendingTimer = window.setTimeout(rematch, delay === undefined ? 400 : delay);
        }

        fetch(suggestionsUrl + "?exclude=" + encodeURIComponent(excludeSlug))
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                articles = (data.articles || []).filter(function (a) {
                    return a.title && a.title.trim().length > 1;
                });
                rematch();
            })
            .catch(function () {
                // No suggestions available — the editor still works fine
                // without this convenience feature.
            });

        textarea.addEventListener("input", function () {
            scheduleRematch(400);
        });
        textarea.addEventListener("scroll", function () {
            if (currentMatches.length) {
                renderHints();
            }
        });
        window.addEventListener("resize", function () {
            if (currentMatches.length) {
                renderHints();
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
        wireWikiLinkHints(form, textarea);
    });
})();
