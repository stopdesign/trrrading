import {React, ReactDOM, html} from "./deps.js";
import Dashboard from "./dashboard.js";


ReactDOM.render(
  html`<${Dashboard} account=${window.account_id} />`,
  document.getElementById("root")
);
