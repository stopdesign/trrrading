import { html, useState, useEffect } from "./deps.js"


const Position = ({ data, curSymbol, setSymbol }) => {

  let amount = ""
  let row_class = "zero"
  if (data.amount > 0) {
    amount += "+" + data.amount
    row_class = "long"
  } else if (data.amount < 0) {
    amount += "−" + (-data.amount)
    row_class = "short"
  } else {
    amount += 0
  }
  if (data.symbol === curSymbol) {
    row_class += " active"
  }

  let pnl = ""
  if (data.unrealized_pnl > 0) {
    pnl += "+" + data.unrealized_pnl
  } else if (data.unrealized_pnl < 0) {
    pnl += "−" + (-data.unrealized_pnl)
  } else {
    pnl += "0"
  }

  return html`
      <tr
              onClick=${() => setSymbol(data.symbol === curSymbol ? "" : data.symbol)}
              className=${row_class}
      >
          <td>${data.name}</td>
          <td className="amount">${amount}</td>
          <td>${data.avg_price}</td>
          <td>${pnl}</td>
      </tr>
  `
}


const Positions = ({ account, symbol, setSymbol }) => {
  const [positions, setPositions] = useState([])

  const fetchPositions = () => {
    fetch('/dash/positions?account=' + account)
      .then(function (response) {
        return response.json()
      })
      .then(function (res_json) {
        setPositions(res_json)
      })
  }

  useEffect(() => {
    setSymbol()
    fetchPositions()
    const interval = setInterval(() => fetchPositions(), 3000)
    return () => {
      clearInterval(interval)
    }
  }, [account])

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
  `
}


export default Positions
