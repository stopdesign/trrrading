import {html, React, useState, useEffect} from "./deps.js";


const Position = ({data, curSymbol, setSymbol}) => {
  return html`
      <tr
              onClick=${() => setSymbol(data.symbol === curSymbol ? "" : data.symbol)}
              className=${data.symbol === curSymbol ? "active" : ""}
      >
          <td>${data.symbol}</td>
          <td>${data.amount}</td>
          <td>${data.avg_price}</td>
          <td>${data.unrealized_pnl}</td>
      </tr>
  `;
}


const Positions = ({account, symbol, setSymbol}) => {
  const [positions, setPositions] = useState([]);

  const fetchPositions = () => {
    fetch('/dash/positions?account=' + account)
      .then(function (response) {
        return response.json();
      })
      .then(function (res_json) {
        setPositions(res_json);
      });
  }

  useEffect(() => {
    setSymbol()
    fetchPositions();
    const interval = setInterval(() => fetchPositions(), 3000);
    return () => {
      clearInterval(interval);
    };
  }, [account]);

  return html`
      <div className="positions_panel">
          <table className="positions">
              <thead>
              <tr>
                  <td>instrument</td>
                  <td>amount</td>
                  <td>price</td>
                  <td>P&L</td>
              </tr>
              </thead>
              <tbody>
              ${positions.map((pos, i) => html`
                  <${Position} data=${pos} curSymbol=${symbol}
                               setSymbol=${setSymbol} key=${i}/>
              `)}
              </tbody>
          </table>
      </div>
  `;
}


export default Positions;
