(function () {
    "use strict";

    var searchInput = document.querySelector("[data-sidebar-article-search]");
    var list = document.querySelector("[data-sidebar-article-list]");
    if (!searchInput || !list) {
        return;
    }

    var pendingTimer = null;
    var currentRequest = 0;

    function escapeHtml(text) {
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function render(articles) {
        if (!articles.length) {
            list.innerHTML = '<li class="text-secondary">Ничего не найдено.</li>';
            return;
        }
        list.innerHTML = articles
            .map(function (article) {
                var url = "/articles/" + encodeURIComponent(article.slug) + "/";
                return (
                    '<li><a href="' + url + '" title="' + escapeHtml(article.title) + '">' +
                    escapeHtml(article.title) +
                    "</a></li>"
                );
            })
            .join("");
    }

    function load(query) {
        var requestId = ++currentRequest;
        fetch("/articles/sidebar-list/?q=" + encodeURIComponent(query))
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                if (requestId !== currentRequest) {
                    return; // a newer request already superseded this one
                }
                render(data.articles || []);
            })
            .catch(function () {
                if (requestId === currentRequest) {
                    list.innerHTML = '<li class="text-secondary">Не удалось загрузить список.</li>';
                }
            });
    }

    searchInput.addEventListener("input", function () {
        if (pendingTimer) {
            window.clearTimeout(pendingTimer);
        }
        var query = searchInput.value;
        pendingTimer = window.setTimeout(function () {
            load(query);
        }, 300);
    });

    load("");
})();
