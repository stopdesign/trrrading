import {html, React, useState, useEffect} from "./deps.js";


const Strategy = ({data, curStrategy, setStrategy}) => {
  return html`
      <tr
              onClick=${() => setStrategy(data.id)}
              className=${data.id === curStrategy ? "active" : ""}
      >
          <td>${data.instrument}</td>
          <td>${data.strategy}</td>
      </tr>
  `;
}


const Strategies = ({curResult, curStrategy, setStrategy}) => {
  const [strategies, setStrategies] = useState([]);

  const fetchData = () => {
    fetch('/bt/strategies?result=' + curResult)
      .then(function (response) {
        return response.json();
      })
      .then(function (res_json) {
        setStrategies(res_json);
      });
  }

  useEffect(() => {
    if (strategies && strategies.length) {
      if (!curStrategy) setStrategy(strategies[0].id);
    } else {
      setStrategy(null);
    }
  }, [strategies]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => fetchData(), 5000);
    return () => {
      setStrategy(null);
      clearInterval(interval);
    };
  }, [curResult]);

  return html`
      <div className="strategies_panel panel">
          <table className="strategies">
              <thead>
              <tr>
                  <td>instrument</td>
                  <td>strategy</td>
              </tr>
              </thead>
              <tbody>
              ${strategies.map((el, i) => html`
                  <${Strategy} data=${el} curStrategy=${curStrategy}
                               setStrategy=${setStrategy} key=${i}/>
              `)}
              </tbody>
          </table>
      </div>
  `;
}


export default Strategies;
