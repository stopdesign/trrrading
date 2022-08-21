import {React, html, useState} from "./deps.js";
import BacktestCharts from "./d3_chart_bt.js";
import Backtests from "./backtests.js"
import Strategies from "./strategies.js"

const DashboardBt = ({results}) => {

  const [result, setResult] = useState(null);
  const [strategy, setStrategy] = useState(null);

  return html`
      <div className="dashboard">
          <div className="left_sidebar">
              <div className="logo_panel">
                  <div className="logo">
                      <div className="logo_text">TRRRADING</div>
                  </div>
              </div>
              <${Backtests} curResult=${result} setResult=${setResult} results=${results} />
          </div>
          <div className="second_sidebar">
            <${Strategies} curResult=${result} curStrategy=${strategy} setStrategy=${setStrategy} />
          </div>
          <div className="main">
              <${BacktestCharts} curResult=${result} curStrategy=${strategy} />
          </div>
      </div>
  `;
}


export default DashboardBt;
