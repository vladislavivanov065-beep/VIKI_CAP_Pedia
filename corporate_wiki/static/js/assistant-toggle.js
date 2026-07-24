(function () {
    "use strict";

    document.querySelectorAll("[data-assistant-toggle-checkbox]").forEach(function (checkbox) {
        checkbox.addEventListener("change", function () {
            var form = checkbox.closest("form");
            if (form) {
                form.submit();
            }
        });
    });
})();
