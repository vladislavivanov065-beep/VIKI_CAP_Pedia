(function () {
    "use strict";

    var DEBOUNCE_MS = 300;
    var MIN_CHARS = 2;

    var input = document.querySelector("[data-search-suggestions]");
    if (!input) {
        return;
    }
    var list = document.querySelector("[data-suggestions-list]");
    var url = input.getAttribute("data-suggestions-url");
    var timer = null;

    function hide() {
        list.hidden = true;
        list.innerHTML = "";
    }

    function render(suggestions) {
        list.innerHTML = "";
        if (!suggestions.length) {
            hide();
            return;
        }
        suggestions.forEach(function (item) {
            var li = document.createElement("li");
            var a = document.createElement("a");
            a.href = item.url;
            a.textContent = item.title;
            li.appendChild(a);
            list.appendChild(li);
        });
        list.hidden = false;
    }

    function fetchSuggestions(query) {
        fetch(url + "?q=" + encodeURIComponent(query))
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                render(data.suggestions || []);
            })
            .catch(hide);
    }

    input.addEventListener("input", function () {
        var query = input.value.trim();
        window.clearTimeout(timer);
        if (query.length < MIN_CHARS) {
            hide();
            return;
        }
        timer = window.setTimeout(function () {
            fetchSuggestions(query);
        }, DEBOUNCE_MS);
    });

    document.addEventListener("click", function (event) {
        if (!input.contains(event.target) && !list.contains(event.target)) {
            hide();
        }
    });
})();
