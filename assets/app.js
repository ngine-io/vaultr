// Small behaviours layered on Tabler. Both handlers are delegated from the document
// because htmx replaces the result fragment after every encryption, so the elements
// they act on do not all exist at load time.
(function () {
  "use strict";

  // --- Theme switch ---------------------------------------------------------
  //
  // Tabler's own tabler-theme.js applies the theme on load, reading the
  // `tabler-theme` localStorage key and falling back to the system preference. It
  // picks up a `?theme=` parameter too, which is what the navbar links use as a
  // no-JavaScript fallback. Handling the click here instead avoids a page
  // navigation, so an encryption result stays on screen when the theme is changed.
  document.addEventListener("click", function (event) {
    var trigger = event.target.closest("[data-set-theme]");
    if (!trigger) {
      return;
    }

    event.preventDefault();
    var theme = trigger.getAttribute("data-set-theme");
    document.documentElement.setAttribute("data-bs-theme", theme);
    try {
      localStorage.setItem("tabler-theme", theme);
    } catch (error) {
      // Private mode or blocked storage: the theme still applies for this page.
    }
  });

  // --- Copy buttons ---------------------------------------------------------
  function flash(button, text) {
    var label = button.querySelector("[data-copy-label]") || button;
    var original = label.textContent;
    label.textContent = text;
    setTimeout(function () {
      label.textContent = original;
    }, 1500);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy-target]");
    if (!button) {
      return;
    }

    var source = document.getElementById(button.getAttribute("data-copy-target"));
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
          source.select();
          flash(button, "Press Ctrl+C");
        }
      );
    } else {
      source.select();
      flash(button, "Press Ctrl+C");
    }
  });
})();
