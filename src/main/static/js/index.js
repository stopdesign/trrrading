import {React, ReactDOM, html} from "./deps.js";
import Dashboard from "./dashboard.js";


ReactDOM.render(
  html`<${Dashboard} accounts=${window["accounts"]} />`,
  document.getElementById("root")
);
