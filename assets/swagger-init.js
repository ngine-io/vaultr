// Starts Swagger UI on the API docs page. FastAPI's built-in page loads Swagger UI
// from a CDN and starts it with an inline script, and the Content Security Policy
// allows neither, so the bundle is served from /static and started from this file.
(function () {
  "use strict";

  var element = document.getElementById("swagger-ui");
  window.ui = SwaggerUIBundle({
    url: element.dataset.openapiUrl,
    dom_id: "#swagger-ui",
    layout: "BaseLayout",
    deepLinking: true,
    showExtensions: true,
    showCommonExtensions: true,
    // Validation would send the schema to validator.swagger.io.
    validatorUrl: null,
    presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
  });
})();
