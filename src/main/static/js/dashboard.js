import {React, html, useState} from "./deps.js";
import Positions from "./positions.js";
import Account from "./account.js";
import Orders from "./orders.js";
import Health from "./health.js";


const Dashboard = ({account}) => {

  const [symbol, setSymbol] = useState();

  return html`
      <div className="dashboard">
          <div className="left_sidebar">
              <${Health} key="1"/>
              <${Account} account=${account} key="2"/>
              <${Positions} account=${account} symbol=${symbol} setSymbol=${setSymbol}
                            key="3"/>
          </div>
          <div className="main">
              <${Orders} account=${account} symbol=${symbol}/>
          </div>
      </div>
  `;
}


export default Dashboard;
