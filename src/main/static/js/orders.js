import {React, html, useEffect, useState} from "./deps.js";


const draw_order = function (ac, order) {
  let color;
  let icon_shape;
  let arrow_pos;

  let price = parseFloat(order["price"]);

  if (order["side"] === "buy") {
    color = "#080";
    icon_shape = "0xf0d8";
    arrow_pos = price - 0.2; // - (range_range/20);
  } else {
    color = "#d00";
    icon_shape = "0xf0d7";
    arrow_pos = price + 0.2; // + (range_range/20);
  }

  const arrow_bg = ac.createShape(
    {time: order["time"], price: price},
    {
      shape: 'icon',
      overrides: {color: "#fff", size: 26, scale: 1},
      icon: icon_shape,
      zOrder: "top",
      disableSelection: true,
    }
  );
  const arrow = ac.createShape(
    {time: order["time"], price: price},
    {
      shape: 'icon',
      overrides: {color: color, size: 20, scale: 1},
      icon: icon_shape,
      zOrder: "top",
      disableSelection: true,
    }
  );
}


const create_chart = (el) => {
  // noinspection JSPotentiallyInvalidConstructorUsage
  window.tv = new TradingView.widget({
    debug: false,
    fullscreen: false,
    symbol: "A",
    interval: "1",
    container: el,
    datafeed: new Datafeeds.UDFCompatibleDatafeed("/tv"),
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
      "right_bar_stays_on_scroll",
    ],
    width: "100%",
    height: "500px",
    toolbar_bg: '#f4f7f9',
  });
}


const Order = ({data, curOrder, setOrder}) => {
  return html`
      <tr onClick=${() => setOrder(data.id === curOrder.id ? {} : data)}
          className=${data.id === curOrder.id ? "active" : ""}
      >
          <td>${data["order_id"]}</td>
          <td>${data["local_id"]}</td>
          <td>${data.symbol}</td>
          <td>${data.side}</td>
          <td>${data.amount}</td>
          <td>${data.filled}</td>
          <td>${data.price}</td>
          <td>${data.status}</td>
          <td>${data.created}</td>
      </tr>
  `;
}


const draw_orders = (orders) => {
  const ac = window.tv.chart();
  const range = ac.getVisibleRange();

  // Удалить все ордеры с графика
  ac.getAllShapes().forEach(({id, name}) => {
    if (name === "icon") {
      ac.removeEntity(id);
    }
  });

  // Нарисовать все видимые ордеры
  for (const order of orders) {
    if (range.from < order["time"] && order["time"] < range.to) {
      // console.log("DRAW", order.time)
      draw_order(ac, order);
    }
  }
}


const Orders = ({account, symbol}) => {
  const [orders, setOrders] = useState([]);
  const [time, setTime] = useState();
  const [selectedOrder, setSelectedOrder] = useState({});
  const [selectionOnChart, setSelectionOnChart] = useState();

  const [dataLoaded, setDataLoaded] = useState();

  // Создание графика при старте
  useEffect(() => {

    console.error("create a chart");
    create_chart("tv_chart_container");

    window.tv.onChartReady(() => {
      const ac = window.tv.chart();
      const ser = ac.getSeries();

      ser.setChartStyleProperties(0, {
        "upColor": "#999",
        "downColor": "#999",
        "barColorsOnPrevClose": false,
        "dontDrawOpen": false,
      })

      ac.applyOverrides({"mainSeriesProperties.style": 0})
      ac.applyOverrides({"mainSeriesProperties.showPriceLine": false})
      ac.applyOverrides({"paneProperties.topMargin": '5'})
      ac.applyOverrides({"paneProperties.bottomMargin": '5'})

      // ac.setVisibleRange({
      //   from: 1648242900,
      //   to: 1648242900
      // }, {applyDefaultRightMargin: true});

      ac.onDataLoaded().subscribe(
        null,
        () => {
          // console.log("onDataLoaded")
          setDataLoaded((new Date()).toISOString())
        },
        false
      );
    });

  }, []);

  // Запуск таймера при создании и остановка при уничтожении компонента
  useEffect(() => {
    const interval = setInterval(() => setTime((new Date()).toISOString()), 5500);
    return () => {
      clearInterval(interval);
    };
  }, []);

  // Сработал таймер
  useEffect(() => {
    fetchOrders(symbol);
  }, [time]);

  // Изменились ордеры или прогрузился очередной кусок графика
  useEffect(() => {
    if (dataLoaded) {
      draw_orders(orders);
    } else {
      console.warn("No chart");
    }
  }, [orders, dataLoaded])

  const fetchOrders = (symbol) => {
    const symbol_str = symbol || "";
    fetch(`/dash/orders?account=${account}&symbol=${symbol_str}`)
      .then(function (response) {
        return response.json();
      })
      .then(function (res_json) {
        // Перезаписывать только при изменениях
        if (JSON.stringify(orders) !== JSON.stringify(res_json)) {
          setOrders(res_json);
        }
      });
  }

  // Изменился symbol
  useEffect(() => {
    setSelectedOrder({});
    console.log("useEffect fetchOrders")
    const chartDiv = document.getElementById("tv_chart_container");
    if (symbol) {
      // Показать график и выставить новый символ
      const ac = window.tv.activeChart();
      // удалить всё с графика
      ac.getAllShapes().forEach(({id, name}) => ac.removeEntity(id));
      ac.setSymbol(symbol);
      chartDiv.style.display = 'block';
      // Дернуть перерисовку ордеров
      if (ac && dataLoaded) {
        draw_orders(orders);
      }
    } else {
      // Скрыть график
      chartDiv.style.display = 'none';
    }
    fetchOrders(symbol);
  }, [symbol]);

  // Выбрали новый order
  useEffect(() => {
    console.log("selectedOrder", selectedOrder.id, selectionOnChart);
    if (selectedOrder && selectedOrder.time) {
      const ac = window.tv.activeChart();
      const id = ac.createShape({time: selectedOrder.time}, {shape: 'vertical_line'});
      if (selectionOnChart) {
        ac.removeEntity(selectionOnChart);
      }
      setSelectionOnChart(id);
    } else {
      if (selectionOnChart) {
        const ac = window.tv.activeChart();
        ac.removeEntity(selectionOnChart);
        setSelectionOnChart();
      }
    }
  }, [selectedOrder])

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
                      <td>side</td>
                      <td>amount</td>
                      <td>filled</td>
                      <td>price</td>
                      <td>status</td>
                      <td>created</td>
                  </tr>
                  </thead>
                  <tbody>
                  ${orders.map((data, i) => html`
                      <${Order}
                              data=${data}
                              curOrder=${selectedOrder}
                              setOrder=${setSelectedOrder}
                              key=${i}
                      />
                  `)}
                  </tbody>
              </table>
          </div>
      </div>
  `;
}


export default Orders;
