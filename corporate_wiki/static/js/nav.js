(function () {
    "use strict";

    var toggle = document.querySelector(".topbar__menu-toggle");
    if (!toggle) {
        return;
    }

    toggle.addEventListener("click", function () {
        var isOpen = document.body.classList.toggle("nav-open");
        toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && document.body.classList.contains("nav-open")) {
            document.body.classList.remove("nav-open");
            toggle.setAttribute("aria-expanded", "false");
            toggle.focus();
        }
    });
})();
