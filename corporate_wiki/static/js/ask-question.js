(function () {
    "use strict";

    // UI scaffold only — no backend yet. Answering questions is a future
    // feature; this just confirms the interaction so the input isn't a
    // dead end.
    document.querySelectorAll("[data-ask-question-form]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            var note = form.querySelector("[data-ask-question-note]");
            if (note) {
                note.hidden = false;
            }
        });
    });
})();
