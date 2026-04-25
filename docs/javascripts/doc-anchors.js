// Make API reference doc headings clickable permalink anchors
document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".doc.doc-heading[id]").forEach(function (heading) {
        heading.style.cursor = "pointer";
        heading.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            var id = heading.getAttribute("id");
            // Update URL hash
            history.pushState(null, "", "#" + id);
            // Scroll to element
            heading.scrollIntoView({ behavior: "smooth", block: "start" });
        });
    });
});
