import {html, useEffect, useState} from "./deps.js";


const draw_order = function (ac, order) {
  let color;
  let icon_shape;
  let arrow_pos;

  let price = parseFloat(order["price"]);

  // let range = ac.getVisiblePriceRange();
  // let range_range = range.to - range.from;

  if (order["side"] === "buy") {
    color = "#080";
    icon_shape = "0xf176";
    arrow_pos = price; // - (range_range/20);
  } else {
    color = "#d00";
    icon_shape = "0xf175";
    arrow_pos = price; // + (range_range/20);
  }

  const arrow = ac.createShape(
    {time: order["time"], price: arrow_pos},
    {
      shape: 'icon',
      overrides: {color: color, size: 17, scale: 1.1},
      icon: icon_shape,
      zOrder: "top",
      disableSelection: true,
    }
  );
  const icon_bg = ac.createShape(
    {time: order["time"], price: price},
    {
      shape: 'icon',
      overrides: {color: "#fff", size: 12, scale: 1},
      icon: '0xf111',
      zOrder: "top",
      disableSelection: true,
    }
  );
  const icon = ac.createShape(
    {time: order["time"], price: price},
    {
      shape: 'icon',
      overrides: {color: color, size: 6, scale: 1},
      icon: '0xf111',
      zOrder: "top",
      disableSelection: true,
    }
  );
}


const Order = ({data}) => {

  const clickMe = (aaa) => {
    console.log(aaa);
  }

  const ac = window.tv.activeChart();
  console.log(data);
  // draw_order(ac, data);

  return html`
      <tr onClick=${() => clickMe(data.symbol)}>
          <td>${data["order_id"]}</td>
          <td>${data["local_id"]}</td>
          <td>${data.symbol}</td>
          <td>${data.amount}</td>
          <td>${data.filled}</td>
          <td>${data.status}</td>
          <td>${data.created}</td>
      </tr>
  `;
}


const Orders = ({account}) => {
  const [orders, setOrders] = useState([]);

  useEffect(() => {

    // noinspection JSPotentiallyInvalidConstructorUsage
    window.tv = new TradingView.widget({
      debug: false,
      fullscreen: false,
      symbol: 'AAPL.NASDAQ',
      interval: '5',
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
      width: "100%",
      height: "500px",
      toolbar_bg: '#f4f7f9',
    });

    window.tv.onChartReady(function () {
      const ac = window.tv.chart();
      const ser = ac.getSeries();

      ac.applyOverrides({"mainSeriesProperties.style": 0})
      ac.applyOverrides({"mainSeriesProperties.showPriceLine": false})
      ac.applyOverrides({"paneProperties.topMargin": '5'})
      ac.applyOverrides({"paneProperties.bottomMargin": '5'})

      ser.setChartStyleProperties(0, {
        "upColor": "#999",
        "downColor": "#999",
        "barColorsOnPrevClose": false,
        "dontDrawOpen": false,
        "thinBars": true
      })
      ser.setChartStyleProperties(2, {
        "color": "#999",
        "linestyle": 0,
        "linewidth": 1,
        "priceSource": "close",
        "styleType": 1  // 1 — квадратная линия, 2 — обычная линия
      })

      ac.setVisibleRange({
        from: 1647894000,
        to: 1648242900
      }, {applyDefaultRightMargin: true});

      // ac.onDataLoaded().subscribe(
      //   null,
      //   () => draw_orders(ac),
      //   false
      // );
    });


  }, []);

  useEffect(() => {
    const interval = setInterval(() => fetchOrders(), 5000);
    return () => {
      clearInterval(interval);
    };
  }, []);

  const fetchOrders = () => {
    console.log("fetchOrders")
    fetch('http://127.0.0.1:8000/dash/orders?account=' + account)
      .then(function (response) {
        return response.json();
      })
      .then(function (res_json) {
        setOrders(res_json);
      });
  }

  useEffect(() => {
    fetchOrders()
  }, []);

  return html`
      <div className="orders_and_chart">
          <div id="tv_chart_container"></div>
          <div className="orders">
              <table>
                  <thead>
                  <tr>
                      <td>order_id</td>
                      <td>local_id</td>
                      <td>symbol</td>
                      <td>amount</td>
                      <td>filled</td>
                      <td>status</td>
                      <td>created</td>
                  </tr>
                  </thead>
                  <tbody>
                  ${orders.map((data, i) => html`
                      <${Order} data=${data} key=${i}/>
                  `)}
                  </tbody>
              </table>
          </div>
      </div>
  `;
}


export default Orders;
