'use strict'

import {React, ReactDOM, html} from "./deps.js";
import Positions from "./positions.js";
import Account from "./account.js";
import Orders from "./orders.js";


ReactDOM.render(
  html`
      <${Account} account=5 key="1"/>
      <${Positions} account=5 key="2"/>
      <${Orders} account=5 key="3"/>
  `,
  document.getElementById("root")
);
