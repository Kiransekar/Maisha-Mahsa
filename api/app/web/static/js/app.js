// Minimal progressive enhancement (no build step). HTMX handles all data flow; this only
// adds the keyboard shortcut to focus the Ask Maisha bar.
(function () {
  function focusAsk(e) {
    // "/" or Cmd/Ctrl+K focuses the Ask bar, unless the user is already typing in a field.
    var el = document.getElementById("ask-input");
    if (!el) return;
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    var slash = e.key === "/" && !typing;
    var cmdK = (e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey);
    if (slash || cmdK) {
      e.preventDefault();
      el.focus();
      el.select();
    }
  }
  document.addEventListener("keydown", focusAsk);
})();
