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


const Account = ({ account }) => {
  const [values, setValues] = React.useState({})

  React.useEffect(() => {
    const interval = setInterval(() => fetchData(), 1000)
    return () => {
      clearInterval(interval)
    }
  }, [])

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
    fetchData()
  }, [])

  return html`
      <div className="account_panel">
          <p>Account:  ${values.uid}</p>
          <p>Last Connected:  ${values["last_connected"]}</p>
          <br/>
          <p>Net Value:  ${values["net_value"]}</p>
          <p>Margin Used:  ${values["margin_used"]}</p>
          <p>Unrealized PnL:  ${values["unrealized_pnl"]}</p>
      </div>
  `
}


export default Account
