import {React, ReactDOM, html} from "./deps.js";
import DashboardBt from "./dashboard_bt.js";


ReactDOM.render(
  html`<${DashboardBt} results=${window.backtest_results} />`,
  document.getElementById("root")
);
