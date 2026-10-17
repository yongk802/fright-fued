/* Ask only the actual opener to populate this private pairing window. */
(() => {
  "use strict";
  document.getElementById("phonePairClose").onclick = () => window.close();
  if (window.opener)
    window.opener.postMessage({ type: "ff-pair-ready" }, location.origin);
})();
