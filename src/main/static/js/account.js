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

  return html`
      <div className=account_panel>
          <p>Account:  ${account_uid}</p>
          <div className=connections>
            ${connections.map(con => html`<div key=${con[0]}>
                <b>${con[0]}</b> - <span className="status status-${con[1]}">${con[1]}</span>
              </div>`)}
          </div>
          <br/>
          <p>Net Value:  ${values["net_value"]}</p>
          <p>Margin Used:  ${values["margin_used"]}</p>
          <p>Unrealized PnL:  ${values["unrealized_pnl"]}</p>
      </div>
  `
}


export default Account
