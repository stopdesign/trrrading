import {html, React} from "./deps.js";


const Position = ({data}) => {

  const clickMe = (aaa) => {

    window.tv.setSymbol(aaa, "1");

  }

  return html`
      <tr onClick=${() => clickMe(data.symbol)}>
          <td>${data.symbol}</td>
          <td>${data.amount}</td>
          <td>${data.avg_price}</td>
          <td>${data.unrealized_pnl}</td>
      </tr>
  `;
}


const Positions = ({account}) => {
  const [positions, setPositions] = React.useState([]);

  const fetchPositions = () => {
    fetch('http://127.0.0.1:8000/dash/positions?account=' + account)
      .then(function (response) {
        return response.json();
      })
      .then(function (res_json) {
        setPositions(res_json);
      });
  }

  React.useEffect(() => {
    fetchPositions();
    const interval = setInterval(() => fetchPositions(), 5000);
    return () => {
      clearInterval(interval);
    };
  }, []);

  return html`
      <div className="positions_panel">
          <table className="positions">
              <thead>
              <tr>
                  <td>symbol</td>
                  <td>amount</td>
                  <td>price</td>
                  <td>P&L</td>
              </tr>
              </thead>
              <tbody>
              ${positions.map((pos, i) => html`
                  <${Position} data=${pos} key=${i}/>
              `)}
              </tbody>
          </table>
      </div>
  `;
}


export default Positions;
