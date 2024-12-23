// Copy buttons for the generated vault string and YAML snippet.
//
// The handler is delegated from the document because htmx replaces the result
// fragment after every encryption, so the buttons do not exist at load time.
(function () {
  "use strict";

  function flash(button, text) {
    var original = button.textContent;
    button.textContent = text;
    setTimeout(function () {
      button.textContent = original;
    }, 1500);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy-target]");
    if (!button) {
      return;
    }

    var source = document.getElementById(button.dataset.copyTarget);
    if (!source) {
      return;
    }

    // navigator.clipboard needs a secure context; fall back to selecting the text
    // so the user can copy it manually over plain HTTP.
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(source.value).then(
        function () {
          flash(button, "Copied");
        },
        function () {
          flash(button, "Press Ctrl+C");
          source.select();
        }
      );
    } else {
      source.select();
      flash(button, "Press Ctrl+C");
    }
  });
})();
