import {html, useEffect, useState, useRef} from "./deps.js";


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
  for (const ex of order.executions) {
    // console.log(order, execution)

    if (!ac.trades.includes(ex["id"])) {

      ac.trades.push(ex["id"])

      const price = parseFloat(ex["price"])

      const arrow_bg = ac.createShape(
        {time: ex["time"], price: price},
        {
          shape: 'icon',
          overrides: {color: "#fff", size: 26, scale: 1},
          icon: icon_shape,
          zOrder: "top",
          disableSelection: true,
        }
      )
      const arrow = ac.createShape(
        {time: ex["time"], price: price},
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
    // FIXME: убрать хардкодинг адреса
    datafeed: new Datafeeds.UDFCompatibleDatafeed("http://10.0.10.1:8080/tv"),
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


const draw_orders = (ac, orders) => {
  const range = ac.getVisibleRange();

  // если графика нет, то рисовать на нем не надо
  if (range["from"] == 0) {
    return
  }

  // Удалить ордеры с графика
  for (const chart_order of ac.orders) {
    chart_order.remove()
  }
  const chart_orders = []

  // Нарисовать все видимые ордеры
  for (const order of orders) {
    // Ордер со сделками
    if (order.executions.length > 0) {
      draw_trade(ac, order);
    }
    // Активный ордер (еще не весь исполнен)
    if (order.status.includes("Submitted")) {
      chart_orders.push(draw_order(ac, order))
    }
  }

  ac.orders = chart_orders
}


const Orders = ({account, symbol}) => {
  const [orders, setOrders] = useState([]);
  const [time, setTime] = useState();
  const [selectedOrder, setSelectedOrder] = useState({});
  const [selectionOnChart, setSelectionOnChart] = useState();
  const [dataLoaded, setDataLoaded] = useState();
  const [resized, setResized] = useState(false);
  const [ac, setActiveChart] = useState();
  const [loading, setLoading] = useState(true);
  const controllerRef = useRef();
  const symbolRef = useRef();


  const fetchOrders = (symbol) => {
    if (controllerRef.current) {
      controllerRef.current.abort()
    }

    const controller = new AbortController()
    controllerRef.current = controller

    const symbol_str = symbol || ""
    fetch(`/dash/orders?account=${account}&symbol=${symbol_str}`, {
      signal: controllerRef.current ? controllerRef.current.signal : null
    })
      .then(
        (response) => {
          response.json().then((res_json) => {
            setLoading(false)
            setOrders(res_json)
            controllerRef.current = null;
          })
        },
        () => { console.warn("fetch failed") }
      )
  }

  // Создание графика при старте
  useEffect(() => {

    console.error("create a chart");
    create_chart("tv_chart_container");

    window["tv"].onChartReady(() => {
      const _ac = window["tv"].activeChart()
      const ser = _ac.getSeries()

      ser.setChartStyleProperties(0, {
        "upColor": "#999",
        "downColor": "#999",
        "barColorsOnPrevClose": false,
        "dontDrawOpen": false,
      })
      ser.setUserEditEnabled(false)

      _ac.applyOverrides({"mainSeriesProperties.style": 0})
      _ac.applyOverrides({"paneProperties.topMargin": '10'})
      _ac.applyOverrides({"paneProperties.bottomMargin": '5'})

      // _ac.onSymbolChanged().subscribe(null, () => {
      //   console.log('The symbol was changed')
      // });

      _ac.dataReady(() => {
        console.log('Data ready')
      });

      _ac.onDataLoaded().subscribe(
        null,
        () => {
          console.log('Data loaded')
          const range = _ac.getVisibleRange();
          if (range.to) {
            setDataLoaded((new Date()).toISOString())
          }
        },
        false
      )

      _ac.orders = []
      _ac.trades = []

      setActiveChart(_ac)

      if (symbolRef.current) {
        _ac.setSymbol(symbolRef.current)
      }
    });

    // Запуск таймера при создании и остановка при уничтожении компонента
    const interval = setInterval(() => setTime((new Date()).toISOString()), 3500);

    return () => {
      clearInterval(interval);
      if (controllerRef.current) controllerRef.current.abort()
    };

  }, []);

  // Сработал таймер
  useEffect(() => {
    fetchOrders(symbol)
  }, [time]);

  // Изменились ордеры или прогрузился очередной кусок графика
  useEffect(() => {

    if (ac && (orders.length > 500 || ac.trades.length > 500)) {
      alert("too many orders or trades too show")
    }

    // Масштабировать график по времени при первой загрузке данных
    if (ac && dataLoaded && !resized) {
      console.warn("first time");
      const to = ac.getVisibleRange().to;
      ac.setVisibleRange(
        {from: to - 3600 * 3, to: to},
        {applyDefaultRightMargin: true}
      );
      setResized(true);
    }

    if (ac && ac.dataReady()) {
      draw_orders(ac, orders);
    } else {
      console.warn("No chart");
    }
  }, [orders, dataLoaded])

  // Изменился symbol
  useEffect(() => {
    setSelectedOrder({});

    symbolRef.current = symbol;

    const chartDiv = document.getElementById("tv_chart_container");
    if (symbol) {
      // Поменять символ на графике
      if (ac) {
        ac.getAllShapes().forEach(({id, name}) => ac.removeEntity(id));
        ac.setSymbol(symbol)
        ac.trades = []
      }
      chartDiv.style.display = 'block';
    } else {
      // Скрыть график
      chartDiv.style.display = 'none';
    }

    setLoading(true)

    // начать загрузку ордеров (если символа нет, то всех)
    fetchOrders(symbol)

    return () => {
      if (controllerRef.current) controllerRef.current.abort()
    }
  }, [symbol]);

  // Выбрали новый order
  useEffect(() => {
    if (!ac) return
    if (selectedOrder && selectedOrder.time) {
      if (selectedOrder.executions.length > 0) {  // есть сделки
        const execution = selectedOrder.executions[0]
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
      } else {
        if (selectionOnChart) {
          ac.removeEntity(selectionOnChart);
          setSelectionOnChart();
        }
      }
    } else {
      if (selectionOnChart) {
        ac.removeEntity(selectionOnChart);
        setSelectionOnChart();
      }
    }
  }, [selectedOrder])

  return html`
      <div className="orders_and_chart">
          <div id="tv_chart_container"></div>
          <div className="orders ${loading ? 'loading' : ''}">
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
