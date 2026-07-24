(function () {
    "use strict";

    var toggle = document.querySelector("[data-theme-toggle]");
    if (!toggle) {
        return;
    }

    function currentTheme() {
        var saved = document.documentElement.dataset.theme;
        if (saved === "dark" || saved === "light") {
            return saved;
        }
        return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }

    toggle.addEventListener("click", function () {
        var next = currentTheme() === "dark" ? "light" : "dark";
        document.documentElement.dataset.theme = next;
        localStorage.setItem("theme", next);
    });
})();
