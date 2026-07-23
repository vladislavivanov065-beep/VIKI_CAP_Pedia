(function () {
    "use strict";

    var toc = document.querySelector(".toc");
    if (!toc || typeof IntersectionObserver === "undefined") {
        return;
    }

    var links = Array.prototype.slice.call(toc.querySelectorAll("a[href^='#']"));
    if (!links.length) {
        return;
    }

    var linkByHeadingId = {};
    var headings = [];
    links.forEach(function (link) {
        var id = link.getAttribute("href").slice(1);
        var heading = document.getElementById(id);
        if (heading) {
            linkByHeadingId[id] = link;
            headings.push(heading);
        }
    });

    function setCurrent(id) {
        links.forEach(function (link) {
            link.classList.remove("toc__current");
        });
        var current = linkByHeadingId[id];
        if (current) {
            current.classList.add("toc__current");
        }
    }

    var observer = new IntersectionObserver(
        function (entries) {
            var visible = entries.filter(function (entry) {
                return entry.isIntersecting;
            });
            if (visible.length > 0) {
                visible.sort(function (a, b) {
                    return a.boundingClientRect.top - b.boundingClientRect.top;
                });
                setCurrent(visible[0].target.id);
            }
        },
        { rootMargin: "0px 0px -70% 0px", threshold: 0 }
    );

    headings.forEach(function (heading) {
        observer.observe(heading);
    });
})();
