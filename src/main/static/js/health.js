import {html, React} from "./deps.js";


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


const Health = () => {

  const [values, setValues] = React.useState({})

  const fetchData = () => {
    fetchWithTimeout("http://10.0.10.1:8080/health_summary")
      .then(function (response) {
        return response.json()
      })
      .then(function (res_json) {
        setValues(res_json)
      })
  }

  React.useEffect(() => {
    const interval = setInterval(() => fetchData(), 5000)

    fetchData()

    return () => {
      clearInterval(interval)
    }
  }, [])

  const report = Object.entries((values && values.total) || {})
  let total = 0
  for (const [_, v] of report) total += v

  return html`
      <div className="health_panel">
          <h3>Tradis</h3>
          ${report.map(([k, v]) => {
            const val = Math.round(v / total * 100).toFixed(0)
            return v > 0 && html`<span>${k}: ${val}%</span>, `
          })}
      </div>
  `;
}


export default Health;
