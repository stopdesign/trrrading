import {html, React} from "./deps.js";
// import './App.css';


const Position = ({ data }) => {

  const clickMe = (aaa) => {

    window.tv.setSymbol(aaa, "1");

  }

  return (
    html`
        <li onClick=${() => clickMe(data.symbol)}>
            <span>${data.symbol}</span>,
            amnt: <span>${data.amount}</span>
        </li>`
  );
}


const Positions = ({ account }) => {
  const [positions, setPositions] = React.useState([]);

  React.useEffect(() => {

    window.tv = new TradingView.widget({
      debug: false,
      fullscreen: false,
      symbol: 'A',
      interval: '1',
      container: "tv_chart_container",

      datafeed: new Datafeeds.UDFCompatibleDatafeed("http://127.0.0.1:8000/tv"),
      library_path: "/static/admin/js/charting_library/",
      locale: "en",
      disabled_features: [
        "symbol_search_hot_key",
        "symbol_search",
        "left_toolbar",
        "control_bar",
        "edit_buttons_in_legend",
        "header_widget",
        "pane_context_menu",
        "scales_context_menu",
        "legend_context_menu",
        "timeframes_toolbar",
      ],
    });

    const interval = setInterval(() => fetchPositions(), 5000);
    return () => {
      clearInterval(interval);
    };
  }, []);

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
    fetchPositions()
  }, []);

  return (
    html`
        <div>
            <h4>Positions</h4>
            <ul>
                ${positions.map((pos, i) => html`<${Position} data=${pos} key=${i} />`)}
            </ul>
            <h4>Chart</h4>
            <div id="tv_chart_container"></div>
        </div>`
  );
}


export default Positions;
