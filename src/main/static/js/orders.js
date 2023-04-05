import {React, html, useEffect, useState} from "./deps.js";


const draw_trade = function (ac, order) {
  let color
  let icon_shape

  // console.log(order.executions)

  if (order["side"] === "buy") {
    color = "#080";
    icon_shape = "0xf0d8";
  } else {
    color = "#d00";
    icon_shape = "0xf0d7";
  }

  // Сделки
  for (const execution of order.executions) {
    // console.log(order, execution)

    const price = parseFloat(execution["price"])

    const arrow_bg = ac.createShape(
      {time: execution["time"], price: price},
      {
        shape: 'icon',
        overrides: {color: "#fff", size: 26, scale: 1},
        icon: icon_shape,
        zOrder: "top",
        disableSelection: true,
      }
    )
    const arrow = ac.createShape(
      {time: execution["time"], price: price},
      {
        shape: 'icon',
        overrides: {color: color, size: 20, scale: 1},
        icon: icon_shape,
        zOrder: "top",
        disableSelection: true,
      }
    )

  }

}


const draw_order = function (ac, order) {
  let color

  if (order["side"] === "buy") {
    color = "#080";
  } else {
    color = "#d00";
  }

  const stop_price = parseFloat(order["stop_price"])
  const limit_price = parseFloat(order["limit_price"])

  let or = ac.createOrderLine()
    .setText(order["type"] + ", " + order["side"])
    .setLineColor(color)
    .setQuantityBackgroundColor(color)
    .setBodyBorderColor(color)
    .setQuantityBorderColor(color)
    .setBodyBackgroundColor('#ffffff')
    .setBodyTextColor(color)
    .setLineWidth(1)
    .setQuantity(order["amount"])
    .setPrice(stop_price)

  console.log(or)

  return or

}

const create_chart = (el) => {
  const Datafeeds = window["Datafeeds"]

  // noinspection JSPotentiallyInvalidConstructorUsage
  // https://github.com/serdimoa/charting/blob/master/Featuresets.md
  window["tv"] = new TradingView.widget({
    debug: false,
    fullscreen: false,
    symbol: "A",
    interval: "1",
    container: el,
    datafeed: new Datafeeds.UDFCompatibleDatafeed("/tv"),
    library_path: "/static/admin/js/charting_library/",
    locale: "en",
    enabled_features: [
      // "disable_resolution_rebuild",
      "high_density_bars",
    ],
    disabled_features: [
      "symbol_search_hot_key",
      "symbol_search",
      "left_toolbar",
      "control_bar",
      "edit_buttons_in_legend",
      // "chart_zoom", "chart_scroll",
      "header_settings",
      "header_compare",
      "header_screenshot",
      "header_fullscreen_button",
      "header_undo_redo",
      "header_indicators",
      "header_symbol_search",
      "compare_symbol",
      "symbol_info",
      "property_pages",
      "display_market_status",
      "remove_library_container_border",
      "uppercase_instrument_names",
      "border_around_the_chart",
      "pane_context_menu",
      "scales_context_menu",
      "legend_context_menu",
      "timeframes_toolbar",
      "right_bar_stays_on_scroll",
    ],
    width: "100%",
    height: "480px",
    toolbar_bg: '#f4f7f9',
  });

  // const iframe = document.getElementById("tv_chart_container").getElementsByTagName("iframe")[0]
  // iframe.contentDocument.body.style.fontFamily = "Hack";

}


const Order = ({data, curOrder, setOrder}) => {

  let price = data.price
  try {
    price = data.price.toFixed(2)
  } catch {
    price = data.price
  }

  return html`
      <tr onClick=${() => setOrder(data.id === curOrder.id ? {} : data)}
          className=${data.id === curOrder.id ? "active" : ""}
      >
          <td>${data["order_id"]}</td>
          <td>${data["local_id"]}</td>
          <td>${data.sid}</td>
          <td>${data.side}</td>
          <td>${data.type}</td>
          <td>${data.amount}</td>
          <td>${data.filled}</td>
          <td>${data.stop_price}</td>
          <td>${data.limit_price}</td>
          <td>${price}</td>
          <td>${data.status}</td>
          <td>${data.created}</td>
      </tr>
  `;
}


const draw_orders = (orders, activeOrdersOnChart, setActiveOrdersOnChart) => {
  const ac = window["tv"].chart();
  const range = ac.getVisibleRange();

  // Удалить сделки с графика
  ac.getAllShapes().forEach(({id, name}) => {
    if (name === "icon" || name === "trend_line") {
      ac.removeEntity(id);
    }
  });

  // Удалить ордеры с графика
  for (const chart_order of activeOrdersOnChart) {
    chart_order.remove()
  }
  const chart_orders = []

  // Нарисовать все видимые ордеры
  for (const order of orders) {
    // Ордер со сделками
    if (range.from < order["time"] && order["time"] < range.to && order.executions.length > 0) {
      draw_trade(ac, order);
    }
    // Активный ордер (еще не весь исполнен)
    if (order.status.includes("Submitted")) {
      chart_orders.push(draw_order(ac, order))
    }
  }

  // Записать список ордеров, чтобы было что удалять
  setActiveOrdersOnChart(chart_orders)
}


const Orders = ({account, symbol}) => {
  const [orders, setOrders] = useState([]);
  const [time, setTime] = useState();
  const [selectedOrder, setSelectedOrder] = useState({});
  const [selectionOnChart, setSelectionOnChart] = useState();

  const [activeOrdersOnChart, setActiveOrdersOnChart] = useState([]);

  const [dataLoaded, setDataLoaded] = useState();

  const [resized, setResized] = useState(false);

  // Создание графика при старте
  useEffect(() => {

    console.error("create a chart");
    create_chart("tv_chart_container");

    window["tv"].onChartReady(() => {
      const ac = window["tv"].chart();
      const ser = ac.getSeries();

      ser.setChartStyleProperties(0, {
        "upColor": "#999",
        "downColor": "#999",
        "barColorsOnPrevClose": false,
        "dontDrawOpen": false,
      })

      ac.applyOverrides({"mainSeriesProperties.style": 0})
      ac.applyOverrides({"paneProperties.topMargin": '10'})
      ac.applyOverrides({"paneProperties.bottomMargin": '5'})

      ac.onDataLoaded().subscribe(
        null,
        () => {
          const range = ac.getVisibleRange();
          if (range.to) {
            setDataLoaded((new Date()).toISOString())
          }
        },
        false
      );
    });

  }, []);

  // Запуск таймера при создании и остановка при уничтожении компонента
  useEffect(() => {
    const interval = setInterval(() => setTime((new Date()).toISOString()), 3500);
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

    if (dataLoaded && !resized) {
      console.warn("first time");
      const ac = window["tv"].chart();
      const to = ac.getVisibleRange().to;
      ac.setVisibleRange(
        // Сколько данных показывать по умолчанию
        {from: to - 3600 * 3, to: to},
        {applyDefaultRightMargin: true}
      );
      setResized(true);
    }

    if (dataLoaded) {
      draw_orders(orders, activeOrdersOnChart, setActiveOrdersOnChart);
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
      const ac = window["tv"].activeChart();
      // удалить всё с графика
      ac.getAllShapes().forEach(({id, name}) => ac.removeEntity(id));
      ac.setSymbol(symbol);
      chartDiv.style.display = 'block';
      // Дернуть перерисовку ордеров
      if (ac && dataLoaded) {
        draw_orders(orders, activeOrdersOnChart, setActiveOrdersOnChart);
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
      if (selectedOrder.executions.length > 0) {  // есть сделки
        const execution = selectedOrder.executions[0]
        const ac = window["tv"].activeChart();
        const id = ac.createShape(
          {
            time: execution.time
          }, {
            shape: 'vertical_line',
            overrides: {linecolor: "#058"},
            disableSelection: true,
          });
        if (selectionOnChart) {
          ac.removeEntity(selectionOnChart);
        }
        console.log(execution)
        setSelectionOnChart(id);
      }
    } else {
      if (selectionOnChart) {
        const ac = window["tv"].activeChart();
        ac.removeEntity(selectionOnChart);  // removeAllShapes
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
                      <td>instrument</td>
                      <td>side</td>
                      <td>type</td>
                      <td>amount</td>
                      <td>filled</td>
                      <td>stop price</td>
                      <td>limit price</td>
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
