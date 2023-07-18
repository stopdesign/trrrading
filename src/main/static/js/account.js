import { html, React } from "./deps.js"


async function fetchWithTimeout(resource, options = {}) {
  const { timeout = 500 } = options

  const controller = new AbortController()
  const id = setTimeout(() => controller.abort(), timeout)
  const response = await fetch(resource, {
    ...options,
    signal: controller.signal
  })
  clearTimeout(id)
  return response
}


const DataFarms = ({ market, historical }) => {

  return html`
    ${(market || historical) && html`<h3>Data Farms</h3>`}

    ${market && Object.entries(market).map(([k, v], i) => html`
      <div key="market_farm_${i}">
        <div>Market ${k}</div>
        <div class="status-${v}">${v}</div>
      </div>
    `)}

    ${historical && Object.entries(historical).map(([k, v], i) => html`
      <div key="market_farm_${i}">
        <div>Historical ${k}</div>
        <div class="status-${v}">${v}</div>
      </div>
    `)}

  `
}


const Gateway = ({ status }) => {
  const con = status["connections"] || {}
  const ibc_login = String(status["ibc_login"]).toLowerCase()

  return html`
    <div>
      <div>IBC auth</div>
      <div class="status-${ibc_login}">${ibc_login}</div>
    </div>
    <div>
      <div>API Server</div>
      <div class="status-${con["IB API Server"]}">${con["IB API Server"]}</div>
    </div>
    <div>
      <div>API Clients</div>
      <div>${con["API Client"]}</div>
    </div>

    ${con && html`<${DataFarms} market=${con["Market Data Farm"]} historical=${con["Historical Data Farm"]} />`}
  `
}


const Account = ({ account, account_uid }) => {
  const [values, setValues] = React.useState({})

  const fetchData = () => {
    fetchWithTimeout('/dash/account?account=' + account)
      .then(function (response) {
        return response.json()
      })
      .then(function (res_json) {
        setValues(res_json)
      })
  }

  React.useEffect(() => {
    const interval = setInterval(() => fetchData(), 1000)

    fetchData()

    return () => {
      clearInterval(interval)
    }
  }, [account])


  const delay = Math.round(parseFloat(values["update_delay"]) / 60) || 0

  let pnl = ""
  if (values.unrealized_pnl > 0) {
    pnl += "+" + values.unrealized_pnl
  } else if (values.unrealized_pnl < 0) {
    pnl += "−" + (-values.unrealized_pnl)
  } else {
    pnl += "0"
  }

  return html`
      <div className=account_panel>

          <h3>
            Gateway
            <span className="delay ${delay > 3 && 'long_delay'}">sync delay ${delay} min</span>
          </h3>

          ${values["gw_status"] && html`<${Gateway} status=${values["gw_status"]}/>`}


          <h3>Account</h3>
          <div>
            <div>Net Liquidation Value</div>
            <div className="value-net_value">${values["net_value"]}</div>
          </div>
          <div>
            <div>Maintainance Margin</div>
            <div className="value-margin_used">${values["margin_used"]}</div>
          </div>
          <div>
            <div>Unrealized PnL</div>
            <div className="value-pnl">${pnl}</div>
          </div>

      </div>
  `
}


export default Account
