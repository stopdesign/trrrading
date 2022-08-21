import { html, React, useState, useEffect } from "./deps.js"


const Backtest = ({ data, curResult, setResult }) => {
  return html`
    <tr
      onClick=${() => setResult(data)}
      className=${data === curResult ? "active" : ""}
    >
      <td>${data.replace('_', ', ')}</td>
    </tr>
  `
}


const Backtests = ({ curResult, setResult }) => {

  const [results, setResults] = useState([])

  const fetchData = () => {
    fetch('/bt/results')
      .then((response) => {
        return response.json()
      })
      .then((res_json) => {
        setResults(res_json["results"])
      })
  }

  useEffect(() => {
    // console.log("Mount Backtests")
    fetchData()

    const interval = setInterval(() => fetchData(), 3000)

    // Specify how to clean up after this effect:
    return () => {
      console.log("Unmount Backtests")
      clearInterval(interval)
    }
  }, [])

  useEffect(() => {
    // Пришел список бэктестов, но ни один еще не выбран
    if (results.length && !curResult) {
      setResult(results[0])
    }
  }, [results])

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
  `
}


export default Backtests
