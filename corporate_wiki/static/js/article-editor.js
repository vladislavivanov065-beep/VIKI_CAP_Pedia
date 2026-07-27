(function () {
    "use strict";

    function getCsrfToken() {
        var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return input ? input.value : "";
    }

    function escapeRegExp(text) {
        return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    // Keep in sync with IMAGE_ALIGN_CLASSES/IMAGE_SIZE_CLASSES in
    // apps/articles/markdown_ext.py — the fixed set of layout presets a
    // ![[image:...]] embed can carry.
    var IMAGE_ALIGN_CLASSES = {
        left: "wiki-image--align-left",
        right: "wiki-image--align-right",
        center: "wiki-image--align-center",
    };
    var IMAGE_SIZE_CLASSES = {
        small: "wiki-image--size-small",
        medium: "wiki-image--size-medium",
        large: "wiki-image--size-large",
        full: "wiki-image--size-full",
    };
    var ALIGN_CLASS_TO_KEY = invert(IMAGE_ALIGN_CLASSES);
    var SIZE_CLASS_TO_KEY = invert(IMAGE_SIZE_CLASSES);

    function invert(obj) {
        var out = {};
        Object.keys(obj).forEach(function (key) {
            out[obj[key]] = key;
        });
        return out;
    }

    // Our custom [[...]] / ![[...]] syntax has no escaping mechanism of
    // its own for "|" and "]" inside a title/caption segment (unlike the
    // rest of Markdown) — strip them so a stray pipe/bracket in typed
    // text can never break the embed syntax on save.
    function stripSyntaxDelimiters(text) {
        return (text || "").replace(/[|\]]/g, "");
    }

    /* ------------------------------------------------------------------
     * DOM -> Markdown serialization (runs once, right before form submit)
     * ------------------------------------------------------------------ */

    // Characters that are structurally significant to Markdown/our syntax
    // if left unescaped inside plain typed text. python-markdown treats a
    // leading backslash before these as a literal escape, so round-tripping
    // arbitrary user text (which knows nothing about Markdown) stays exact.
    function escapeInlineText(text) {
        return text.replace(/([\\`*_~[\]{}])/g, "\\$1");
    }

    // Escapes markers that are only special at the very start of a line
    // (heading #, list -/+, blockquote >, ordered list "1.", table |) so
    // plain paragraphs that happen to start with one of these characters
    // aren't misread as structure when re-rendered. Each check requires
    // the same trailing-space-or-boundary Markdown itself requires, so
    // this never touches "**bold**"/"`code`" markers we generated
    // ourselves (those have already been through escapeInlineText, at
    // the point their plain-text pieces were assembled — re-escaping the
    // composed string here would corrupt them).
    function escapeLineStart(line) {
        var result = line;
        result = result.replace(/^(\s*)(#{1,6})(\s|$)/, "$1\\$2$3");
        result = result.replace(/^(\s*)>/, "$1\\>");
        result = result.replace(/^(\s*)([-+])(\s)/, "$1\\$2$3");
        result = result.replace(/^(\s*)(\d+)\.(\s)/, "$1$2\\.$3");
        result = result.replace(/^(\s*)\|/, "$1\\|");
        return result;
    }

    function escapeParagraphText(text) {
        return text.split("\n").map(escapeLineStart).join("\n");
    }

    // Serializes the inline (phrasing) content of a node: text, bold,
    // italic, strikethrough, inline code, line breaks, and links
    // (external + wiki-links, using the data-wiki-* attributes set by the
    // server renderer / inserted by the editor to survive round-tripping
    // without guessing a title back from a slug).
    function serializeInline(node) {
        var out = "";
        node.childNodes.forEach(function (child) {
            if (child.nodeType === Node.TEXT_NODE) {
                out += escapeInlineText((child.textContent || "").replace(/\n/g, " "));
                return;
            }
            if (child.nodeType !== Node.ELEMENT_NODE) {
                return;
            }
            var tag = child.tagName.toLowerCase();
            switch (tag) {
                case "strong":
                case "b":
                    out += "**" + serializeInline(child) + "**";
                    break;
                case "em":
                case "i":
                    out += "*" + serializeInline(child) + "*";
                    break;
                case "del":
                case "s":
                case "strike":
                    out += "~~" + serializeInline(child) + "~~";
                    break;
                case "code":
                    out += "`" + (child.textContent || "") + "`";
                    break;
                case "br":
                    out += "  \n";
                    break;
                case "a":
                    out += serializeLink(child);
                    break;
                case "span": {
                    var inner = serializeInline(child);
                    var color = colorToHex(child.style.color);
                    var background = colorToHex(child.style.backgroundColor);
                    if (color) {
                        inner = "{color:" + color + "}" + inner + "{/color}";
                    }
                    if (background) {
                        inner = "{bg:" + background + "}" + inner + "{/bg}";
                    }
                    out += inner;
                    break;
                }
                default:
                    // Unknown inline wrapper (e.g. a stray <span>) — keep
                    // its content rather than silently dropping it.
                    out += serializeInline(child);
            }
        });
        return out;
    }

    // Keep in sync with COLOR_RE/BACKGROUND_COLOR_RE in
    // apps/articles/markdown_ext.py, which only ever accepts a six-digit
    // hex value -- normalizes whatever the browser reports for
    // style.color/backgroundColor (hex or "rgb(r, g, b)", depending on
    // engine) into that exact format. Returns null for anything else
    // (including "" when no colour is set), so a plain <span> with no
    // colour styling is left alone by the two callers above.
    function colorToHex(value) {
        if (!value) {
            return null;
        }
        var hexMatch = /^#([0-9a-f]{6})$/i.exec(value.trim());
        if (hexMatch) {
            return "#" + hexMatch[1].toLowerCase();
        }
        var rgbMatch = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i.exec(value.trim());
        if (!rgbMatch) {
            return null;
        }
        return (
            "#" +
            [1, 2, 3]
                .map(function (i) {
                    return Number(rgbMatch[i]).toString(16).padStart(2, "0");
                })
                .join("")
        );
    }

    // Matches the "\U0001f4ce " (📎) prefix AttachmentEmbedInlineProcessor
    // always prepends server-side — stripped back out before
    // re-serializing so round-tripping an attachment link never
    // accumulates a second paperclip on top of the first.
    var ATTACHMENT_ICON_PREFIX = "📎 ";

    function serializeLink(anchor) {
        var display = serializeInline(anchor) || anchor.textContent || "";
        var articleId = anchor.getAttribute("data-wiki-article-id");
        var uuid = anchor.getAttribute("data-wiki-uuid");
        var title = anchor.getAttribute("data-wiki-title");
        var attachmentId = anchor.getAttribute("data-attachment-id");

        if (attachmentId) {
            var attachmentDisplay = stripSyntaxDelimiters(display);
            if (attachmentDisplay.indexOf(ATTACHMENT_ICON_PREFIX) === 0) {
                attachmentDisplay = attachmentDisplay.slice(ATTACHMENT_ICON_PREFIX.length);
            }
            return "[[attachment:" + attachmentId + "|" + attachmentDisplay + "]]";
        }
        if (articleId) {
            return "[[article:" + articleId + "|" + stripSyntaxDelimiters(display) + "]]";
        }
        if (uuid) {
            return "[[article:" + uuid + "|" + stripSyntaxDelimiters(display) + "]]";
        }
        if (title !== null && title !== undefined) {
            var cleanTitle = stripSyntaxDelimiters(title);
            var cleanDisplay = stripSyntaxDelimiters(display);
            return cleanDisplay && cleanDisplay.toLowerCase() !== cleanTitle.toLowerCase()
                ? "[[" + cleanTitle + "|" + cleanDisplay + "]]"
                : "[[" + cleanTitle + "]]";
        }

        var href = anchor.getAttribute("href") || "";
        return "[" + escapeInlineText(display) + "](" + href + ")";
    }

    function serializeImageFigure(figure) {
        var img = figure.querySelector("img");
        if (!img) {
            return "";
        }
        var imageId = img.getAttribute("data-image-id");
        if (!imageId) {
            return "";
        }
        var figcaption = figure.querySelector("figcaption");
        var caption = stripSyntaxDelimiters(figcaption ? figcaption.textContent || "" : "");

        var options = [];
        (figure.className || "").split(/\s+/).forEach(function (cls) {
            if (ALIGN_CLASS_TO_KEY[cls]) {
                options.push("align=" + ALIGN_CLASS_TO_KEY[cls]);
            } else if (SIZE_CLASS_TO_KEY[cls]) {
                options.push("size=" + SIZE_CLASS_TO_KEY[cls]);
            }
        });

        var body = "image:" + imageId;
        if (caption || options.length) {
            body += "|" + caption;
        }
        if (options.length) {
            body += "|" + options.join(";");
        }
        return "![[" + body + "]]";
    }

    function serializeList(listEl, ordered, depth) {
        var indent = "  ".repeat(depth);
        var lines = [];
        var index = 1;
        Array.prototype.forEach.call(listEl.children, function (li) {
            if (li.tagName.toLowerCase() !== "li") {
                return;
            }
            var nestedList = li.querySelector(":scope > ul, :scope > ol");
            var ownText = "";
            li.childNodes.forEach(function (child) {
                if (child === nestedList) {
                    return;
                }
                if (child.nodeType === Node.TEXT_NODE) {
                    ownText += escapeInlineText(child.textContent || "");
                } else if (child.nodeType === Node.ELEMENT_NODE && child !== nestedList) {
                    var childTag = child.tagName.toLowerCase();
                    if (childTag === "ul" || childTag === "ol") {
                        return;
                    }
                    ownText += serializeInline(wrapSingle(child));
                }
            });
            var marker = ordered ? index + ". " : "- ";
            lines.push(indent + marker + ownText.trim());
            if (nestedList) {
                lines.push(
                    serializeList(
                        nestedList,
                        nestedList.tagName.toLowerCase() === "ol",
                        depth + 1
                    )
                );
            }
            index += 1;
        });
        return lines.join("\n");
    }

    // Wraps a single inline-ish element so serializeInline can walk "its
    // children" uniformly for the one-off case above.
    function wrapSingle(el) {
        var holder = document.createElement("span");
        holder.appendChild(el.cloneNode(true));
        return holder;
    }

    function serializeTableCell(cell) {
        return serializeInline(cell).replace(/\n/g, " ").replace(/\|/g, "\\|").trim();
    }

    function serializeTable(table) {
        var headRow = table.querySelector("thead tr");
        var bodyRows = Array.prototype.slice.call(table.querySelectorAll("tbody tr"));
        if (!headRow) {
            var allRows = Array.prototype.slice.call(table.querySelectorAll("tr"));
            headRow = allRows.shift();
            bodyRows = allRows;
        }
        if (!headRow) {
            return "";
        }
        var headCells = Array.prototype.slice.call(headRow.children).map(serializeTableCell);
        var lines = [
            "| " + headCells.join(" | ") + " |",
            "| " + headCells.map(function () {
                return "---";
            }).join(" | ") + " |",
        ];
        bodyRows.forEach(function (row) {
            var cells = Array.prototype.slice.call(row.children).map(serializeTableCell);
            lines.push("| " + cells.join(" | ") + " |");
        });
        return lines.join("\n");
    }

    function serializeBlock(node) {
        var tag = node.tagName.toLowerCase();
        switch (tag) {
            case "h1":
            case "h2":
            case "h3":
            case "h4":
            case "h5":
            case "h6":
                return "#".repeat(Number(tag[1])) + " " + serializeInline(node).trim();
            case "p":
            case "div":
                // execCommand-driven editing can leave block elements
                // (lists, nested paragraphs) inside what should be a plain
                // <p>/<div> — e.g. exiting a list with a double Enter. If
                // that happened, recurse block-wise instead of flattening
                // everything into one line of "inline" text.
                if (containsBlockChild(node)) {
                    return serializeChildren(node).join("\n\n");
                }
                return escapeParagraphText(serializeInline(node));
            case "blockquote": {
                // Only ever walks inline content (never recurses back into
                // serializeBlock) so a blockquote can never trigger a loop
                // on itself regardless of how the browser structured it.
                var paragraphs = node.querySelectorAll(":scope > p");
                var inner = paragraphs.length
                    ? Array.prototype.map
                          .call(paragraphs, function (p) {
                              return escapeParagraphText(serializeInline(p));
                          })
                          .join("\n\n")
                    : escapeParagraphText(serializeInline(node));
                return inner
                    .split("\n")
                    .map(function (line) {
                        return "> " + line;
                    })
                    .join("\n");
            }
            case "ul":
                return serializeList(node, false, 0);
            case "ol":
                return serializeList(node, true, 0);
            case "pre": {
                var code = node.querySelector("code");
                var text = (code || node).textContent || "";
                return "```\n" + text.replace(/\n+$/, "") + "\n```";
            }
            case "hr":
                return "---";
            case "table":
                return serializeTable(node);
            case "figure":
                return serializeImageFigure(node);
            default:
                return escapeParagraphText(serializeInline(node));
        }
    }

    var BLOCK_TAGS = {
        p: 1, div: 1, h1: 1, h2: 1, h3: 1, h4: 1, h5: 1, h6: 1,
        blockquote: 1, ul: 1, ol: 1, pre: 1, hr: 1, table: 1, figure: 1,
    };

    function containsBlockChild(node) {
        return Array.prototype.some.call(node.children || [], function (child) {
            return BLOCK_TAGS[child.tagName.toLowerCase()];
        });
    }

    // Walks a container's direct children, grouping consecutive inline/
    // text nodes into implicit paragraphs and serializing recognized block
    // elements individually. Shared by the top-level root walk and by
    // serializeBlock's defensive recursion into malformed nesting.
    function serializeChildren(root) {
        var blocks = [];
        var looseBuffer = [];

        function flushLoose() {
            if (!looseBuffer.length) {
                return;
            }
            var holder = document.createElement("span");
            looseBuffer.forEach(function (n) {
                holder.appendChild(n.cloneNode(true));
            });
            var text = escapeParagraphText(serializeInline(holder)).trim();
            if (text) {
                blocks.push(text);
            }
            looseBuffer = [];
        }

        Array.prototype.forEach.call(root.childNodes, function (node) {
            if (node.nodeType === Node.ELEMENT_NODE && BLOCK_TAGS[node.tagName.toLowerCase()]) {
                flushLoose();
                var serialized = serializeBlock(node);
                if (serialized.trim()) {
                    blocks.push(serialized);
                }
            } else if (node.nodeType === Node.TEXT_NODE && !node.textContent.trim()) {
                // ignore whitespace-only stray text between blocks
            } else {
                looseBuffer.push(node);
            }
        });
        flushLoose();

        return blocks;
    }

    function htmlToMarkdown(root) {
        var blocks = serializeChildren(root);
        return blocks.join("\n\n") + (blocks.length ? "\n" : "");
    }

    /* ------------------------------------------------------------------
     * Toolbar (bold/italic/headings/lists/links/wikilinks)
     * ------------------------------------------------------------------ */

    function withSelectionInside(surface, fn) {
        var selection = window.getSelection();
        if (!selection || selection.rangeCount === 0) {
            return;
        }
        var range = selection.getRangeAt(0);
        if (!surface.contains(range.commonAncestorContainer)) {
            return;
        }
        fn(selection, range);
    }

    function wrapRangeWithElement(range, el) {
        try {
            range.surroundContents(el);
        } catch (err) {
            var contents = range.extractContents();
            el.appendChild(contents);
            range.insertNode(el);
        }
        return el;
    }

    function wireToolbar(surface, articlesRef) {
        var toolbar = surface.parentNode.querySelector(".wysiwyg-toolbar");
        if (!toolbar) {
            return;
        }
        try {
            document.execCommand("defaultParagraphSeparator", false, "p");
        } catch (err) {
            // Unsupported in some browsers — Enter still works, just may
            // produce <div> instead of <p>; serializeBlock treats both
            // the same way, so this degrades gracefully.
        }

        toolbar.addEventListener("click", function (event) {
            var button = event.target.closest("[data-cmd]");
            if (!button) {
                return;
            }
            surface.focus();
            var cmd = button.getAttribute("data-cmd");
            switch (cmd) {
                case "bold":
                    document.execCommand("bold");
                    break;
                case "italic":
                    document.execCommand("italic");
                    break;
                case "strike":
                    document.execCommand("strikeThrough");
                    break;
                case "h2":
                    document.execCommand("formatBlock", false, "H2");
                    break;
                case "h3":
                    document.execCommand("formatBlock", false, "H3");
                    break;
                case "paragraph":
                    document.execCommand("formatBlock", false, "P");
                    break;
                case "ul":
                    document.execCommand("insertUnorderedList");
                    break;
                case "ol":
                    document.execCommand("insertOrderedList");
                    break;
                case "blockquote":
                    document.execCommand("formatBlock", false, "BLOCKQUOTE");
                    break;
                case "hr":
                    document.execCommand("insertHorizontalRule");
                    break;
                case "code":
                    withSelectionInside(surface, function (selection, range) {
                        if (range.collapsed) {
                            return;
                        }
                        var el = wrapRangeWithElement(range, document.createElement("code"));
                        selection.removeAllRanges();
                        var next = document.createRange();
                        next.selectNodeContents(el);
                        next.collapse(false);
                        selection.addRange(next);
                    });
                    break;
                case "link":
                    withSelectionInside(surface, function (selection, range) {
                        if (range.collapsed) {
                            return;
                        }
                        var url = window.prompt("Адрес ссылки (https://...)", "https://");
                        if (!url) {
                            return;
                        }
                        var el = document.createElement("a");
                        el.setAttribute("href", url);
                        wrapRangeWithElement(range, el);
                        selection.removeAllRanges();
                    });
                    break;
                case "wikilink":
                    withSelectionInside(surface, function (selection, range) {
                        if (range.collapsed) {
                            return;
                        }
                        var selectedText = range.toString();
                        var matchArticle = (articlesRef.list || []).find(function (a) {
                            return a.title.toLowerCase() === selectedText.trim().toLowerCase();
                        });
                        var el = document.createElement("a");
                        if (matchArticle) {
                            el.setAttribute("class", "wiki-link");
                            el.setAttribute("data-wiki-article-id", matchArticle.id);
                        } else {
                            el.setAttribute("class", "wiki-link-missing");
                            el.setAttribute("data-wiki-title", selectedText.trim());
                        }
                        wrapRangeWithElement(range, el);
                        selection.removeAllRanges();
                    });
                    break;
                default:
                    break;
            }
            syncToolbarState(toolbar);
        });

        function syncToolbarState(toolbarEl) {
            ["bold", "italic", "strike"].forEach(function (cmd) {
                var btn = toolbarEl.querySelector('[data-cmd="' + cmd + '"]');
                if (!btn) {
                    return;
                }
                var queryCmd = cmd === "strike" ? "strikeThrough" : cmd;
                var active = false;
                try {
                    active = document.queryCommandState(queryCmd);
                } catch (err) {
                    active = false;
                }
                btn.classList.toggle("is-active", !!active);
            });
        }

        surface.addEventListener("keyup", function () {
            syncToolbarState(toolbar);
        });
        surface.addEventListener("mouseup", function () {
            syncToolbarState(toolbar);
        });
    }

    /* ------------------------------------------------------------------
     * Image insertion, drag-resize, align mini-toolbar
     * ------------------------------------------------------------------ */

    function guessAltFromFilename(filename) {
        return (filename || "").replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
    }

    function buildImageFigure(imageId, altText, caption, align, size) {
        var figure = document.createElement("figure");
        var classes = [];
        if (align && IMAGE_ALIGN_CLASSES[align]) {
            classes.push(IMAGE_ALIGN_CLASSES[align]);
        }
        if (size && IMAGE_SIZE_CLASSES[size]) {
            classes.push(IMAGE_SIZE_CLASSES[size]);
        }
        figure.className = classes.join(" ");

        var img = document.createElement("img");
        img.setAttribute("src", "/images/" + imageId + "/");
        img.setAttribute("data-image-id", imageId);
        img.setAttribute("alt", altText || "");
        figure.appendChild(img);

        if (caption) {
            var figcaption = document.createElement("figcaption");
            figcaption.textContent = caption;
            figure.appendChild(figcaption);
        }

        augmentFigure(figure);
        return figure;
    }

    // Adds the editor-only resize handle to a figure that came from
    // server-rendered HTML (which never includes it — that markup is
    // shared with the public article page), and makes the whole figure an
    // atomic, non-editable unit. Without contenteditable="false" here, the
    // browser's caret can land *inside* the figure (e.g. via the End key),
    // silently splitting typed text into the figure's own subtree —
    // invisible in the editor's rendering (it inherits the figure's
    // centered layout) and silently dropped on save, since the serializer
    // only reads the figure's img/figcaption. Making it atomic rules that
    // out entirely; caption edits go through the mini-toolbar instead.
    function augmentFigure(figure) {
        figure.setAttribute("contenteditable", "false");
        if (figure.querySelector(".wysiwyg-resize-handle")) {
            return;
        }
        var handle = document.createElement("span");
        handle.className = "wysiwyg-resize-handle";
        handle.setAttribute("contenteditable", "false");
        handle.setAttribute("aria-hidden", "true");
        figure.appendChild(handle);
    }

    function insertNodeAtSelection(surface, node) {
        surface.focus();
        var selection = window.getSelection();
        var range;
        if (selection && selection.rangeCount > 0 && surface.contains(selection.getRangeAt(0).commonAncestorContainer)) {
            range = selection.getRangeAt(0);
        } else {
            range = document.createRange();
            range.selectNodeContents(surface);
            range.collapse(false);
        }
        range.deleteContents();
        range.insertNode(node);
        range.setStartAfter(node);
        range.collapse(true);
        if (selection) {
            selection.removeAllRanges();
            selection.addRange(range);
        }
    }

    function insertFragmentAtSelection(surface, fragment) {
        surface.focus();
        var selection = window.getSelection();
        var range;
        if (selection && selection.rangeCount > 0 && surface.contains(selection.getRangeAt(0).commonAncestorContainer)) {
            range = selection.getRangeAt(0);
        } else {
            range = document.createRange();
            range.selectNodeContents(surface);
            range.collapse(false);
        }
        range.deleteContents();
        var lastNode = fragment.lastChild;
        range.insertNode(fragment);
        if (lastNode) {
            range.setStartAfter(lastNode);
            range.collapse(true);
            if (selection) {
                selection.removeAllRanges();
                selection.addRange(range);
            }
        }
    }

    /* ------------------------------------------------------------------
     * Paste sanitizing: pasted HTML (e.g. a table copied from Excel/
     * Google Sheets, or formatted text from Word) can carry a lot of
     * markup our serializer doesn't understand and don't want to store —
     * inline styles, classes, colgroups, mso-* junk. Rebuild pasted
     * content from scratch using only the tags the serializer already
     * knows how to turn into Markdown, so a paste behaves exactly like
     * typing the same content by hand.
     * ------------------------------------------------------------------ */

    var PASTE_KEEP_TAGS = {
        p: 1, div: 1, h1: 1, h2: 1, h3: 1, h4: 1, h5: 1, h6: 1,
        strong: 1, b: 1, em: 1, i: 1, u: 1, del: 1, s: 1, code: 1, br: 1,
        ul: 1, ol: 1, li: 1, blockquote: 1, hr: 1,
        table: 1, thead: 1, tbody: 1, tr: 1, th: 1, td: 1,
        a: 1,
    };
    var PASTE_DROP_TAGS = { style: 1, script: 1, meta: 1, link: 1, img: 1, head: 1 };

    function appendCleanedPasteNode(node, targetParent) {
        if (node.nodeType === Node.TEXT_NODE) {
            if (node.textContent) {
                targetParent.appendChild(document.createTextNode(node.textContent));
            }
            return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) {
            return;
        }
        var tag = node.tagName.toLowerCase();
        if (PASTE_DROP_TAGS[tag]) {
            return;
        }
        if (PASTE_KEEP_TAGS[tag]) {
            var clean = document.createElement(tag);
            if (tag === "a") {
                var href = node.getAttribute("href");
                if (href) {
                    clean.setAttribute("href", href);
                }
            }
            Array.prototype.forEach.call(node.childNodes, function (child) {
                appendCleanedPasteNode(child, clean);
            });
            targetParent.appendChild(clean);
            return;
        }
        // Unknown wrapper (span, font, mso-* classed div, ...) — drop the
        // element itself but keep walking into its children, same as the
        // serializer's own "unwrap unrecognized inline tag" fallback.
        Array.prototype.forEach.call(node.childNodes, function (child) {
            appendCleanedPasteNode(child, targetParent);
        });
    }

    function cleanPastedHtml(html) {
        var container = document.createElement("div");
        container.innerHTML = html;
        var fragment = document.createDocumentFragment();
        Array.prototype.forEach.call(container.childNodes, function (node) {
            appendCleanedPasteNode(node, fragment);
        });
        return fragment;
    }

    function wirePasteSanitizer(surface) {
        surface.addEventListener("paste", function (event) {
            var clipboardData = event.clipboardData;
            var html = clipboardData && clipboardData.getData("text/html");
            if (!html) {
                return; // no HTML on the clipboard — default plain-text paste is fine
            }
            event.preventDefault();
            var fragment = cleanPastedHtml(html);
            if (!fragment.childNodes.length) {
                return;
            }
            insertFragmentAtSelection(surface, fragment);
        });
    }

    function uploadImage(file, altText, caption, align, size, onDone) {
        var formData = new FormData();
        formData.append("file", file);
        formData.append("alt_text", altText || "");
        formData.append("caption", caption || "");

        return fetch("/images/upload/", {
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
                    onDone(result.data.id);
                } else {
                    window.alert(result.data.error || "Не удалось загрузить изображение.");
                }
            })
            .catch(function () {
                window.alert("Не удалось загрузить изображение.");
            });
    }

    function wireImageUpload(form, surface) {
        var uploadButton = form.querySelector("[data-image-upload]");
        var fileInput = form.querySelector("[data-image-input]");
        var panel = form.querySelector("[data-image-panel]");
        if (!panel) {
            return;
        }
        var filenameLabel = panel.querySelector("[data-image-filename]");
        var altInput = panel.querySelector("[data-image-alt]");
        var captionInput = panel.querySelector("[data-image-caption]");
        var alignSelect = panel.querySelector("[data-image-align]");
        var sizeSelect = panel.querySelector("[data-image-size]");
        var confirmButton = panel.querySelector("[data-image-confirm]");
        var cancelButton = panel.querySelector("[data-image-cancel]");
        var pendingFile = null;
        var savedRange = null;

        function openPanel(file) {
            pendingFile = file;
            var selection = window.getSelection();
            if (selection && selection.rangeCount > 0 && surface.contains(selection.getRangeAt(0).commonAncestorContainer)) {
                savedRange = selection.getRangeAt(0).cloneRange();
            } else {
                savedRange = null;
            }
            filenameLabel.textContent = file.name;
            altInput.value = guessAltFromFilename(file.name);
            captionInput.value = "";
            if (alignSelect) {
                alignSelect.value = "none";
            }
            if (sizeSelect) {
                sizeSelect.value = "medium";
            }
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

        surface.addEventListener("dragover", function (event) {
            event.preventDefault();
        });
        surface.addEventListener("drop", function (event) {
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
                var align = alignSelect ? alignSelect.value : "none";
                var size = sizeSelect ? sizeSelect.value : "full";
                var caption = captionInput.value.trim();
                var alt = altInput.value.trim();
                confirmButton.disabled = true;
                uploadImage(file, alt, caption, align, size, function (imageId) {
                    var figure = buildImageFigure(imageId, alt, caption, align, size);
                    if (savedRange) {
                        var selection = window.getSelection();
                        selection.removeAllRanges();
                        selection.addRange(savedRange);
                    }
                    insertNodeAtSelection(surface, figure);
                }).then(function () {
                    confirmButton.disabled = false;
                    closePanel();
                });
            });
        }

        if (cancelButton) {
            cancelButton.addEventListener("click", closePanel);
        }
    }

    function buildAttachmentLink(attachmentId, filename) {
        var anchor = document.createElement("a");
        anchor.setAttribute("class", "attachment-link");
        anchor.setAttribute("href", "/attachments/" + attachmentId + "/download/");
        anchor.setAttribute("data-attachment-id", attachmentId);
        anchor.setAttribute("download", filename || "");
        anchor.textContent = ATTACHMENT_ICON_PREFIX + (filename || "Файл");
        return anchor;
    }

    function wireAttachmentUpload(form, surface) {
        var uploadButton = form.querySelector("[data-attachment-upload]");
        var fileInput = form.querySelector("[data-attachment-input]");
        if (!uploadButton || !fileInput) {
            return;
        }
        var savedRange = null;

        uploadButton.addEventListener("click", function () {
            var selection = window.getSelection();
            if (selection && selection.rangeCount > 0 && surface.contains(selection.getRangeAt(0).commonAncestorContainer)) {
                savedRange = selection.getRangeAt(0).cloneRange();
            } else {
                savedRange = null;
            }
            fileInput.click();
        });

        fileInput.addEventListener("change", function () {
            var file = fileInput.files && fileInput.files[0];
            if (!file) {
                return;
            }
            var formData = new FormData();
            formData.append("file", file);

            fetch("/attachments/upload/", {
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
                        var anchor = buildAttachmentLink(result.data.id, result.data.filename);
                        if (savedRange) {
                            var selection = window.getSelection();
                            selection.removeAllRanges();
                            selection.addRange(savedRange);
                        }
                        insertNodeAtSelection(surface, anchor);
                    } else {
                        window.alert(result.data.error || "Не удалось загрузить файл.");
                    }
                })
                .catch(function () {
                    window.alert("Не удалось загрузить файл.");
                })
                .then(function () {
                    fileInput.value = "";
                });
        });
    }

    var SIZE_ORDER = ["small", "medium", "large", "full"];

    function currentSizeKey(figure) {
        for (var i = 0; i < SIZE_ORDER.length; i++) {
            if (figure.classList.contains(IMAGE_SIZE_CLASSES[SIZE_ORDER[i]])) {
                return SIZE_ORDER[i];
            }
        }
        return "full";
    }

    function currentAlignKey(figure) {
        for (var key in IMAGE_ALIGN_CLASSES) {
            if (figure.classList.contains(IMAGE_ALIGN_CLASSES[key])) {
                return key;
            }
        }
        return "none";
    }

    function setFigureSize(figure, sizeKey) {
        Object.keys(IMAGE_SIZE_CLASSES).forEach(function (key) {
            figure.classList.remove(IMAGE_SIZE_CLASSES[key]);
        });
        if (sizeKey && sizeKey !== "full" && IMAGE_SIZE_CLASSES[sizeKey]) {
            figure.classList.add(IMAGE_SIZE_CLASSES[sizeKey]);
        }
    }

    function setFigureAlign(figure, alignKey) {
        Object.keys(IMAGE_ALIGN_CLASSES).forEach(function (key) {
            figure.classList.remove(IMAGE_ALIGN_CLASSES[key]);
        });
        if (alignKey && alignKey !== "none" && IMAGE_ALIGN_CLASSES[alignKey]) {
            figure.classList.add(IMAGE_ALIGN_CLASSES[alignKey]);
        }
    }

    // Drag distance -> size preset. Matches the px caps in style.css
    // (small=200 / medium=350 / large=500 / full≈content width).
    function widthToSizeKey(width) {
        if (width <= 260) {
            return "small";
        }
        if (width <= 430) {
            return "medium";
        }
        if (width <= 620) {
            return "large";
        }
        return "full";
    }

    function wireImageInteractions(surface) {
        Array.prototype.forEach.call(surface.querySelectorAll("figure"), augmentFigure);

        var miniToolbar = null;
        var selectedFigure = null;

        function removeMiniToolbar() {
            if (miniToolbar) {
                miniToolbar.remove();
                miniToolbar = null;
            }
        }

        function deselect() {
            if (selectedFigure) {
                selectedFigure.classList.remove("is-selected");
            }
            selectedFigure = null;
            removeMiniToolbar();
        }

        function showMiniToolbar(figure) {
            removeMiniToolbar();
            miniToolbar = document.createElement("div");
            miniToolbar.className = "wysiwyg-image-toolbar";
            miniToolbar.setAttribute("contenteditable", "false");

            var alignKey = currentAlignKey(figure);
            var sizeKey = currentSizeKey(figure);

            [
                ["none", "Без обтекания"],
                ["left", "Слева"],
                ["right", "Справа"],
                ["center", "По центру"],
            ].forEach(function (pair) {
                var btn = document.createElement("button");
                btn.type = "button";
                btn.textContent = pair[1];
                btn.dataset.action = "align";
                btn.dataset.value = pair[0];
                if (pair[0] === alignKey) {
                    btn.classList.add("is-active");
                }
                miniToolbar.appendChild(btn);
            });

            [
                ["small", "S"],
                ["medium", "M"],
                ["large", "L"],
                ["full", "Во всю ширину"],
            ].forEach(function (pair) {
                var btn = document.createElement("button");
                btn.type = "button";
                btn.textContent = pair[1];
                btn.dataset.action = "size";
                btn.dataset.value = pair[0];
                if (pair[0] === sizeKey) {
                    btn.classList.add("is-active");
                }
                miniToolbar.appendChild(btn);
            });

            var captionBtn = document.createElement("button");
            captionBtn.type = "button";
            captionBtn.textContent = "Подпись";
            captionBtn.dataset.action = "caption";
            miniToolbar.appendChild(captionBtn);

            var deleteBtn = document.createElement("button");
            deleteBtn.type = "button";
            deleteBtn.textContent = "Удалить";
            deleteBtn.dataset.action = "delete";
            miniToolbar.appendChild(deleteBtn);

            document.body.appendChild(miniToolbar);
            positionMiniToolbar(figure);
        }

        function positionMiniToolbar(figure) {
            if (!miniToolbar) {
                return;
            }
            var rect = figure.getBoundingClientRect();
            miniToolbar.style.left = (window.scrollX + rect.left) + "px";
            miniToolbar.style.top = (window.scrollY + rect.top - miniToolbar.offsetHeight - 6) + "px";
        }

        surface.addEventListener("mousedown", function (event) {
            var handle = event.target.closest(".wysiwyg-resize-handle");
            if (handle) {
                startResize(event, handle.closest("figure"));
                return;
            }
            var figure = event.target.closest("figure");
            if (figure && surface.contains(figure)) {
                event.preventDefault();
                deselect();
                selectedFigure = figure;
                figure.classList.add("is-selected");
                showMiniToolbar(figure);
            } else if (!event.target.closest(".wysiwyg-image-toolbar")) {
                deselect();
            }
        });

        document.addEventListener("mousedown", function (event) {
            if (
                selectedFigure &&
                !event.target.closest("figure") &&
                !event.target.closest(".wysiwyg-image-toolbar")
            ) {
                deselect();
            }
        });

        document.addEventListener("click", function (event) {
            if (!miniToolbar) {
                return;
            }
            var button = event.target.closest("[data-action]");
            if (!button || !miniToolbar.contains(button) || !selectedFigure) {
                return;
            }
            var action = button.dataset.action;
            if (action === "align") {
                setFigureAlign(selectedFigure, button.dataset.value);
                showMiniToolbar(selectedFigure);
            } else if (action === "size") {
                setFigureSize(selectedFigure, button.dataset.value);
                showMiniToolbar(selectedFigure);
            } else if (action === "caption") {
                var existing = selectedFigure.querySelector("figcaption");
                var next = window.prompt("Подпись к изображению", existing ? existing.textContent : "");
                if (next === null) {
                    return;
                }
                next = next.trim();
                if (!next) {
                    if (existing) {
                        existing.remove();
                    }
                } else if (existing) {
                    existing.textContent = next;
                } else {
                    var figcaption = document.createElement("figcaption");
                    figcaption.textContent = next;
                    selectedFigure.appendChild(figcaption);
                }
                positionMiniToolbar(selectedFigure);
            } else if (action === "delete") {
                var toRemove = selectedFigure;
                deselect();
                toRemove.remove();
            }
        });

        window.addEventListener("scroll", function () {
            if (selectedFigure) {
                positionMiniToolbar(selectedFigure);
            }
        }, true);
        window.addEventListener("resize", function () {
            if (selectedFigure) {
                positionMiniToolbar(selectedFigure);
            }
        });

        function startResize(event, figure) {
            if (!figure) {
                return;
            }
            event.preventDefault();
            var img = figure.querySelector("img");
            var startX = event.clientX;
            var startWidth = img.getBoundingClientRect().width;

            function onMove(moveEvent) {
                var proposed = startWidth + (moveEvent.clientX - startX);
                setFigureSize(figure, widthToSizeKey(Math.max(proposed, 80)));
                if (selectedFigure === figure) {
                    positionMiniToolbar(figure);
                }
            }
            function onUp() {
                document.removeEventListener("mousemove", onMove);
                document.removeEventListener("mouseup", onUp);
                if (selectedFigure === figure) {
                    showMiniToolbar(figure);
                }
            }
            document.addEventListener("mousemove", onMove);
            document.addEventListener("mouseup", onUp);
        }
    }

    /* ------------------------------------------------------------------
     * Table insertion (rows x columns panel) and per-table mini-toolbar
     * (add/remove row/column, delete table)
     * ------------------------------------------------------------------ */

    function buildTable(rows, cols) {
        var table = document.createElement("table");
        var thead = document.createElement("thead");
        var headRow = document.createElement("tr");
        for (var c = 0; c < cols; c++) {
            headRow.appendChild(document.createElement("th"));
        }
        thead.appendChild(headRow);
        table.appendChild(thead);

        var tbody = document.createElement("tbody");
        for (var r = 1; r < rows; r++) {
            var row = document.createElement("tr");
            for (var c2 = 0; c2 < cols; c2++) {
                row.appendChild(document.createElement("td"));
            }
            tbody.appendChild(row);
        }
        table.appendChild(tbody);
        return table;
    }

    function wireTableInsert(form, surface) {
        var insertButton = form.querySelector("[data-table-insert]");
        var panel = form.querySelector("[data-table-panel]");
        if (!insertButton || !panel) {
            return;
        }
        var rowsInput = panel.querySelector("[data-table-rows]");
        var colsInput = panel.querySelector("[data-table-cols]");
        var confirmButton = panel.querySelector("[data-table-confirm]");
        var cancelButton = panel.querySelector("[data-table-cancel]");
        var savedRange = null;

        insertButton.addEventListener("click", function () {
            var selection = window.getSelection();
            if (selection && selection.rangeCount > 0 && surface.contains(selection.getRangeAt(0).commonAncestorContainer)) {
                savedRange = selection.getRangeAt(0).cloneRange();
            } else {
                savedRange = null;
            }
            panel.hidden = false;
        });

        if (cancelButton) {
            cancelButton.addEventListener("click", function () {
                panel.hidden = true;
            });
        }

        if (confirmButton) {
            confirmButton.addEventListener("click", function () {
                var rows = Math.min(20, Math.max(1, parseInt(rowsInput.value, 10) || 1));
                var cols = Math.min(10, Math.max(1, parseInt(colsInput.value, 10) || 1));
                var table = buildTable(rows, cols);
                if (savedRange) {
                    var selection = window.getSelection();
                    selection.removeAllRanges();
                    selection.addRange(savedRange);
                }
                insertNodeAtSelection(surface, table);
                panel.hidden = true;
            });
        }
    }

    function tableRows(table) {
        return Array.prototype.slice.call(table.querySelectorAll("tr"));
    }

    function cellIndexInRow(cell) {
        return Array.prototype.indexOf.call(cell.parentNode.children, cell);
    }

    function addTableRowAfter(table, referenceRow) {
        var columnCount = referenceRow.children.length;
        var newRow = document.createElement("tr");
        for (var i = 0; i < columnCount; i++) {
            newRow.appendChild(document.createElement("td"));
        }
        var isHeaderRow = referenceRow.parentNode.tagName.toLowerCase() === "thead";
        if (isHeaderRow) {
            var tbody = table.querySelector("tbody");
            if (tbody) {
                tbody.insertBefore(newRow, tbody.firstChild);
            } else {
                table.appendChild(newRow);
            }
        } else {
            referenceRow.parentNode.insertBefore(newRow, referenceRow.nextSibling);
        }
    }

    function deleteTableRow(table, row) {
        var rows = tableRows(table);
        if (rows.length <= 1) {
            return;
        }
        var parent = row.parentNode;
        row.remove();
        if (parent.tagName.toLowerCase() === "thead" && !parent.querySelector("tr")) {
            parent.remove();
        }
    }

    function addTableColumnAfter(table, colIndex) {
        tableRows(table).forEach(function (row) {
            var isHeaderRow = row.parentNode.tagName.toLowerCase() === "thead";
            var cell = document.createElement(isHeaderRow ? "th" : "td");
            var referenceCell = row.children[colIndex];
            if (referenceCell && referenceCell.nextSibling) {
                row.insertBefore(cell, referenceCell.nextSibling);
            } else {
                row.appendChild(cell);
            }
        });
    }

    function deleteTableColumn(table, colIndex) {
        var rows = tableRows(table);
        if (!rows.length || rows[0].children.length <= 1) {
            return;
        }
        rows.forEach(function (row) {
            var cell = row.children[colIndex];
            if (cell) {
                cell.remove();
            }
        });
    }

    function wireTableInteractions(surface) {
        var miniToolbar = null;
        var selectedTable = null;
        var selectedRow = null;
        var selectedColIndex = 0;

        function removeMiniToolbar() {
            if (miniToolbar) {
                miniToolbar.remove();
                miniToolbar = null;
            }
        }

        function deselect() {
            if (selectedTable) {
                selectedTable.classList.remove("is-selected");
            }
            selectedTable = null;
            selectedRow = null;
            removeMiniToolbar();
        }

        function positionMiniToolbar() {
            if (!miniToolbar || !selectedTable) {
                return;
            }
            var rect = selectedTable.getBoundingClientRect();
            miniToolbar.style.left = window.scrollX + rect.left + "px";
            miniToolbar.style.top = window.scrollY + rect.top - miniToolbar.offsetHeight - 6 + "px";
        }

        function showMiniToolbar() {
            removeMiniToolbar();
            miniToolbar = document.createElement("div");
            miniToolbar.className = "wysiwyg-table-toolbar";
            miniToolbar.setAttribute("contenteditable", "false");

            [
                ["add-row", "Добавить строку"],
                ["add-col", "Добавить столбец"],
                ["delete-row", "Удалить строку"],
                ["delete-col", "Удалить столбец"],
                ["delete-table", "Удалить таблицу"],
            ].forEach(function (pair) {
                var btn = document.createElement("button");
                btn.type = "button";
                btn.textContent = pair[1];
                btn.dataset.tableAction = pair[0];
                if (pair[0] === "delete-table") {
                    btn.classList.add("wysiwyg-table-toolbar__danger");
                }
                miniToolbar.appendChild(btn);
            });

            document.body.appendChild(miniToolbar);
            positionMiniToolbar();
        }

        function selectCell(cell) {
            var row = cell.parentNode;
            var table = cell.closest("table");
            if (!table || !surface.contains(table)) {
                return;
            }
            if (selectedTable !== table) {
                deselect();
                selectedTable = table;
                selectedTable.classList.add("is-selected");
            }
            selectedRow = row;
            selectedColIndex = cellIndexInRow(cell);
            showMiniToolbar();
        }

        surface.addEventListener("mousedown", function (event) {
            var cell = event.target.closest("td, th");
            if (cell && surface.contains(cell)) {
                selectCell(cell);
            } else if (!event.target.closest(".wysiwyg-table-toolbar")) {
                deselect();
            }
        });

        document.addEventListener("mousedown", function (event) {
            if (
                selectedTable &&
                !event.target.closest("table") &&
                !event.target.closest(".wysiwyg-table-toolbar")
            ) {
                deselect();
            }
        });

        document.addEventListener("click", function (event) {
            if (!miniToolbar) {
                return;
            }
            var button = event.target.closest("[data-table-action]");
            if (!button || !miniToolbar.contains(button) || !selectedTable || !selectedRow) {
                return;
            }
            var action = button.dataset.tableAction;
            if (action === "add-row") {
                addTableRowAfter(selectedTable, selectedRow);
                positionMiniToolbar();
            } else if (action === "add-col") {
                addTableColumnAfter(selectedTable, selectedColIndex);
                positionMiniToolbar();
            } else if (action === "delete-row") {
                deleteTableRow(selectedTable, selectedRow);
                deselect();
            } else if (action === "delete-col") {
                deleteTableColumn(selectedTable, selectedColIndex);
                deselect();
            } else if (action === "delete-table") {
                var table = selectedTable;
                deselect();
                table.remove();
            }
        });

        window.addEventListener(
            "scroll",
            function () {
                positionMiniToolbar();
            },
            true
        );
        window.addEventListener("resize", positionMiniToolbar);
    }

    /* ------------------------------------------------------------------
     * Font colour / text highlight: native <input type="color"> pickers.
     * Opening the native OS picker steals focus from the contenteditable
     * surface, and in some browsers that alone collapses/clears the
     * document Selection immediately -- before any handler on the color
     * input itself gets a chance to read it. So rather than capturing the
     * selection reactively when the input is clicked, it's tracked
     * continuously while the user is actually working in the surface
     * (mouseup/keyup/selectionchange) and simply left in place; by the
     * time the picker's `input` event fires, whatever was last selected
     * in the surface is still on hand regardless of what focus did.
     * ------------------------------------------------------------------ */

    function wireColorPickers(surface, toolbar) {
        var savedRange = null;

        function trackSelection() {
            var selection = window.getSelection();
            if (
                selection &&
                selection.rangeCount > 0 &&
                surface.contains(selection.getRangeAt(0).commonAncestorContainer) &&
                !selection.getRangeAt(0).collapsed
            ) {
                savedRange = selection.getRangeAt(0).cloneRange();
            }
        }

        surface.addEventListener("mouseup", trackSelection);
        surface.addEventListener("keyup", trackSelection);
        document.addEventListener("selectionchange", trackSelection);

        function applyColor(cssProperty, value) {
            if (!savedRange) {
                return;
            }
            var selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(savedRange);
            var span = document.createElement("span");
            span.style[cssProperty] = value;
            wrapRangeWithElement(savedRange, span);
            selection.removeAllRanges();
            var next = document.createRange();
            next.selectNodeContents(span);
            next.collapse(false);
            selection.addRange(next);
            savedRange = null;
        }

        toolbar.querySelectorAll("[data-color-picker]").forEach(function (input) {
            input.addEventListener("input", function () {
                if (!savedRange) {
                    window.alert("Сначала выделите текст.");
                    return;
                }
                applyColor(input.getAttribute("data-color-picker"), input.value);
            });
        });
    }

    /* ------------------------------------------------------------------
     * Wiki-link hints: underline words matching an existing article title
     * with a small clickable "make this a link" button.
     * ------------------------------------------------------------------ */

    var MAX_HINTS = 60;

    function findTitleMatchesInText(text, articles) {
        if (!articles.length || !text) {
            return [];
        }
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
            pattern = new RegExp("(?<![\\p{L}\\p{N}_])(" + alternation + ")(?![\\p{L}\\p{N}_])", "giu");
        } catch (err) {
            return [];
        }

        var matches = [];
        var match;
        while ((match = pattern.exec(text)) !== null && matches.length < MAX_HINTS) {
            matches.push({
                start: match.index,
                end: match.index + match[0].length,
                matchedText: match[0],
                article: byLowerTitle[match[0].toLowerCase()],
            });
        }
        return matches;
    }

    function eligibleTextNodes(surface) {
        var walker = document.createTreeWalker(surface, NodeFilter.SHOW_TEXT, null);
        var nodes = [];
        var node;
        while ((node = walker.nextNode())) {
            if (node.parentElement && node.parentElement.closest("a, code, pre, figcaption")) {
                continue;
            }
            if (node.textContent && node.textContent.trim()) {
                nodes.push(node);
            }
        }
        return nodes;
    }

    function wireWikiLinkHints(surface, articlesRef) {
        var hintLayer = document.createElement("div");
        hintLayer.className = "wikilink-hint-layer";
        hintLayer.style.position = "absolute";
        hintLayer.style.top = "0";
        hintLayer.style.left = "0";
        hintLayer.style.right = "0";
        hintLayer.style.bottom = "0";
        hintLayer.style.pointerEvents = "none";
        surface.parentNode.style.position = surface.parentNode.style.position || "relative";
        surface.parentNode.insertBefore(hintLayer, surface.nextSibling);

        var pendingTimer = null;

        function render() {
            hintLayer.innerHTML = "";
            var articles = articlesRef.list || [];
            if (!articles.length) {
                return;
            }
            var hostRect = surface.parentNode.getBoundingClientRect();
            eligibleTextNodes(surface).forEach(function (textNode) {
                var matches = findTitleMatchesInText(textNode.textContent, articles);
                matches.forEach(function (m) {
                    var range = document.createRange();
                    range.setStart(textNode, m.start);
                    range.setEnd(textNode, m.end);
                    var rect = range.getBoundingClientRect();
                    if (!rect.width && !rect.height) {
                        return;
                    }
                    var button = document.createElement("button");
                    button.type = "button";
                    button.className = "wikilink-hint";
                    button.style.pointerEvents = "auto";
                    button.title = "Сделать ссылку на статью «" + m.article.title + "»";
                    button.textContent = "🔗";
                    button.style.left = (rect.right - hostRect.left) + "px";
                    button.style.top = (rect.top - hostRect.top) + "px";
                    button.addEventListener("mousedown", function (event) {
                        // Prevent the surface from losing/collapsing selection
                        // before the click handler runs.
                        event.preventDefault();
                    });
                    button.addEventListener("click", function () {
                        convertMatch(textNode, m);
                    });
                    hintLayer.appendChild(button);
                });
            });
        }

        function convertMatch(textNode, m) {
            var range = document.createRange();
            range.setStart(textNode, m.start);
            range.setEnd(textNode, m.end);
            var anchor = document.createElement("a");
            anchor.setAttribute("class", "wiki-link");
            anchor.setAttribute("data-wiki-article-id", m.article.id);
            anchor.textContent = m.matchedText;
            range.deleteContents();
            range.insertNode(anchor);
            scheduleRender(0);
        }

        function scheduleRender(delay) {
            if (pendingTimer) {
                window.clearTimeout(pendingTimer);
            }
            pendingTimer = window.setTimeout(render, delay === undefined ? 500 : delay);
        }

        surface.addEventListener("input", function () {
            scheduleRender(500);
        });
        surface.addEventListener("scroll", function () {
            scheduleRender(0);
        });
        window.addEventListener("resize", function () {
            scheduleRender(0);
        });

        return { render: function () { scheduleRender(0); } };
    }

    /* ------------------------------------------------------------------
     * Wiring per-form: seed initial content, submit-time serialization
     * ------------------------------------------------------------------ */

    function seedInitialContent(form, surface) {
        var template = document.getElementById("article-editor-initial-html");
        if (template && "content" in template) {
            surface.appendChild(template.content.cloneNode(true));
        }
    }

    function wireFormSubmit(form, surface) {
        var textarea = form.querySelector("textarea[name='content_source']");
        if (!textarea) {
            return;
        }
        form.addEventListener("submit", function () {
            textarea.value = htmlToMarkdown(surface);
        });
    }

    document.querySelectorAll("form.article-form").forEach(function (form) {
        var surface = form.querySelector("[data-wysiwyg-surface]");
        if (!surface) {
            return;
        }

        seedInitialContent(form, surface);

        var articlesRef = { list: [] };
        var suggestionsUrl = form.getAttribute("data-link-suggestions-url");
        var excludeSlug = form.getAttribute("data-exclude-slug") || "";
        var hints = null;
        if (suggestionsUrl) {
            fetch(suggestionsUrl + "?exclude=" + encodeURIComponent(excludeSlug))
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    articlesRef.list = (data.articles || []).filter(function (a) {
                        return a.title && a.title.trim().length > 1;
                    });
                    if (hints) {
                        hints.render();
                    }
                })
                .catch(function () {
                    // Suggestions/hints are a convenience feature only.
                });
        }

        wireToolbar(surface, articlesRef);
        wireImageUpload(form, surface);
        wireAttachmentUpload(form, surface);
        wireImageInteractions(surface);
        wireTableInsert(form, surface);
        wireTableInteractions(surface);
        var toolbarEl = surface.parentNode.querySelector(".wysiwyg-toolbar");
        if (toolbarEl) {
            wireColorPickers(surface, toolbarEl);
        }
        wirePasteSanitizer(surface);
        hints = wireWikiLinkHints(surface, articlesRef);
        wireFormSubmit(form, surface);
    });
})();
