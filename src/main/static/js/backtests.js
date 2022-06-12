import {html, React, useState, useEffect} from "./deps.js";


const Backtest = ({data, curResult, setResult}) => {
  return html`
      <tr
              onClick=${() => setResult(data)}
              className=${data === curResult ? "active" : ""}
      >
          <td>${data}</td>
      </tr>
  `;
}


const Backtests = ({results, curResult, setResult}) => {
  return html`
      <div className="results_panel">
          <table className="results">
              <thead>
              <tr>
                  <td>Backtest run</td>
              </tr>
              </thead>
              <tbody>
              ${results.map((res, i) => html`
                  <${Backtest} data=${res} curResult=${curResult} setResult=${setResult} key=${i}/>
              `)}
              </tbody>
          </table>
      </div>
  `;
}


export default Backtests;
