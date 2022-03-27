import {React, ReactDOM, html} from "./deps.js";
import Dashboard from "./dashboard.js";


ReactDOM.render(
  html`<${Dashboard} account=1 />`,
  document.getElementById("root")
);
