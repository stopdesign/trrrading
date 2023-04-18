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


  const connections = values["connections"] || []

  const delay = Math.round(parseFloat(values["update_delay"]) / 60)

  return html`
      <div className=account_panel>
          <div className=account_uid>Account: ${account_uid}
            <span className="delay ${delay >= 1 && 'long_delay'}">delay ${delay} min</span>
          </div>
          <div className=connections>
            ${connections.map(con => html`<div key=${con[0]}>
                <b>${con[0]}</b> - <span className="status status-${con[1]}">${con[1]}</span>
              </div>`)}
          </div>
          <div className=account_values>
            <div>Net Value:  ${values["net_value"]}</div>
            <div>Margin Used:  ${values["margin_used"]}</div>
            <div>Unrealized PnL:  ${values["unrealized_pnl"]}</div>
          </div>
      </div>
  `
}


export default Account
