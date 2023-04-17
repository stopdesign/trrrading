import { html, useEffect, useState, useRef } from "./deps.js"


const draw_trade = function (ac, order, trade) {

  let color
  let icon_shape

  if (order["side"] === "buy") {
    color = "#080"
    icon_shape = "0xf0d8"
  } else {
    color = "#d00"
    icon_shape = "0xf0d7"
  }

  const price = parseFloat(trade["price"])

  ac.createShape(
    { time: trade["time"], price: price },
    {
      shape: 'icon',
      overrides: { color: "#fff", size: 30, scale: 0.8 },
      icon: icon_shape,
      zOrder: "top",
      disableSelection: true,
      disableSave: true,
      disableUndo: true,
      lock: true,
      showInObjectsTree: false,
    }
  )
  ac.createShape(
    { time: trade["time"], price: price },
    {
      shape: 'icon',
      overrides: { color: color, size: 20, scale: 0.9 },
      icon: icon_shape,
      zOrder: "top",
      disableSelection: true,
      disableSave: true,
      disableUndo: true,
      lock: true,
      showInObjectsTree: false,
    }
  )
}


const draw_order = function (ac, order) {
  let color

  if (order.side === "buy") {
    color = "#080"
  } else {
    color = "#d00"
  }

  const stop_price = parseFloat(order["stop_price"])
  const limit_price = parseFloat(order["limit_price"])

  const price = stop_price || limit_price

  let or = ac.createOrderLine()
    .setPrice(price)
    .setTooltip(JSON.stringify(order, null, 4))
    .setBodyFont("bold 11px Hack,-apple-system,Trebuchet MS,Roboto,Ubuntu,sans-serif")
    .setQuantityFont("bold 11px Hack,-apple-system,Trebuchet MS,Roboto,Ubuntu,sans-serif")
    .setText((order.type + " " + order.side + " ").toUpperCase())
    .setQuantity(order.amount)
    .setDirection(order.side)
    .setLineStyle(2)
    .setLineColor(color)
    .setQuantityBackgroundColor(color)
    .setBodyBorderColor(color)
    .setQuantityBorderColor(color)
    .setBodyTextColor(color)
    .setBodyBackgroundColor('#ffffff')
    .setLineLength(2)

  return or

}


const create_chart = (el) => {
  const Datafeeds = window["Datafeeds"]

  // noinspection JSPotentiallyInvalidConstructorUsage
  // https://github.com/serdimoa/charting/blob/master/Featuresets.md
  const chart_widget = new TradingView.widget({
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
      // "property_pages",
      "display_market_status",
      "remove_library_container_border",
      "uppercase_instrument_names",
      "border_around_the_chart",
      "pane_context_menu",
      "scales_context_menu",
      "legend_context_menu",
      "timeframes_toolbar",
      // "right_bar_stays_on_scroll",
    ],
    width: "100%",
    height: "500px",
    toolbar_bg: '#f4f7f9',

    // set local timezone
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  })

  // const iframe = document.getElementById("tv_chart_container").getElementsByTagName("iframe")[0]
  // iframe.contentDocument.body.style.fontFamily = "Hack";

  return chart_widget
}


const Order = ({ data, curOrder, setOrder }) => {

  let price = data.price
  try {
    price = data.price.toFixed(2)
  } catch {
    price = data.price
  }

  let row_class = ""
  if (data.id === curOrder.id) {
    row_class += " active "
  }
  if (typeof data.status == "string") {
    row_class += data.status.toLowerCase()
  }
  let side = typeof data.side == "string" ? data.side.toLowerCase() : ""

  let sid = data.sid
  if (data.oca_group) {
    sid = ""
    row_class += " in_oca_group "
  }

  return html`
      <tr onClick=${() => setOrder(data.id === curOrder.id ? {} : data)}
          className="${row_class}"
      >
          <td className="instrument">${sid}</td>
          <td className="order_id">${data.order_id}</td>
          <td className="local_id">${data.local_id}</td>
          <td className="order_type">
            ${data.algo_strategy && html`<span>${data.algo_strategy}</span>`}
            ${data.type}
          </td>
          <td className="side side-${side}">${side}</td>
          <td className="amount">${data.amount}</td>
          <td className="filled">${data.filled}</td>
          <td>${data.stop_price}</td>
          <td>${data.limit_price}</td>
          <td>${price}</td>
          <td className="status">${data.status}</td>
          <td>${data.created}</td>
      </tr>
  `
}



const Orders = ({ account, symbol }) => {
  const [orders, setOrders] = useState([])
  const [time, setTime] = useState()
  const [selectedOrder, setSelectedOrder] = useState({})
  const [selectionOnChart, setSelectionOnChart] = useState()
  const [dataLoaded, setDataLoaded] = useState()
  const [resized, setResized] = useState(false)
  const [loading, setLoading] = useState(true)
  const controllerRef = useRef()
  const acRef = useRef()
  const ordersRef = useRef([])

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
            ordersRef.current = res_json  // это для графика
            setOrders(res_json)  // это для таблицы
            controllerRef.current = null
          })
        },
        () => { console.warn("fetch failed") }
      )
  }

  // Создание графика при старте
  useEffect(() => {

    const tv = create_chart("tv_chart_container")

    tv.headerReady().then(function () {
      const button = tv.createButton()
      button.setAttribute('title', 'My custom button tooltip')
      button.addEventListener('click', function () {
        console.log("Shapes cnt:", tv.activeChart().getAllShapes().length)
      })
      button.textContent = "Button"
    })

    tv.onChartReady(() => {
      const ac = tv.activeChart()
      const ser = ac.getSeries()

      ac.orders = {}
      ac.trades = []

      acRef.current = ac

      ser.setChartStyleProperties(0, {
        "upColor": "#999",
        "downColor": "#999",
        "barColorsOnPrevClose": false,
        "dontDrawOpen": false,
      })
      ser.setUserEditEnabled(false)

      ac.applyOverrides({ "mainSeriesProperties.style": 0 })
      ac.applyOverrides({ "paneProperties.topMargin": '10' })
      ac.applyOverrides({ "paneProperties.bottomMargin": '5' })

      ac.onDataLoaded().subscribe(
        null,
        () => {
          const range = ac.getVisibleRange()
          if (range.to) {
            setDataLoaded((new Date()).toISOString())
          } else {
            setDataLoaded()
          }
        }
      )

    })

    // Запуск таймера при создании и остановка при уничтожении компонента
    const interval = setInterval(() => setTime((new Date()).toISOString()), 3500)

    return () => {
      clearInterval(interval)
      if (controllerRef.current) controllerRef.current.abort()
    }

  }, [])

  // Сработал таймер
  useEffect(() => {
    fetchOrders(symbol)
  }, [time])

  // Изменились ордеры или прогрузился очередной кусок графика
  useEffect(() => {

    const ac = acRef.current

    if (!(ac && ac.dataReady())) {
      return
    }

    const range = ac.getVisibleRange()

    const visibleOrderIds = []
    for (const order of ordersRef.current) {
      const id = parseInt(order.id)
      if (order.status.includes("Submitted")) {
        visibleOrderIds.push(id)
      }
    }

    // Удалить ордеры, которые сейчас на графике, но не в visibleOrderIds
    for (const [_id, order] of Object.entries(ac.orders)) {
      const id = parseInt(_id)
      if (!visibleOrderIds.includes(id)) {
        order.remove()
      }
    }

    // Нарисовать новые видимые ордеры
    for (const order of ordersRef.current) {
      const id = parseInt(order.id)
      if (visibleOrderIds.includes(id) && !ac.orders[id]) {
        ac.orders[id] = draw_order(ac, order)
      }
    }

    // Сделки
    for (const order of ordersRef.current) {
      for (const trade of order.executions) {
        if (trade.time < range.from || trade.time > range.to) {
          continue
        }
        if (!ac.trades.includes(trade.id)) {
          draw_trade(ac, order, trade)
          ac.trades.push(trade.id)
        }
      }
    }

    // Масштабировать график по времени при первой загрузке данных
    if (dataLoaded && !resized) {
      console.warn("first time")
      const to = ac.getVisibleRange().to
      ac.setVisibleRange(
        { from: to - 3600 * 12, to: to },
        { applyDefaultRightMargin: true }
      )
      setResized(true)
    }

  }, [orders, dataLoaded])

  // Изменился symbol
  useEffect(() => {

    // Показать / скрыть график
    const chartDiv = document.getElementById("tv_chart_container")
    chartDiv.style.display = symbol ? 'block' : 'none'

    setSelectedOrder({})

    // помутнение таблицы
    setLoading(true)

    // очистить список ордеров для графика
    ordersRef.current = []

    // начать загрузку ордеров (если символа нет, то всех)
    fetchOrders(symbol)

    if (acRef.current) {
      const ac = acRef.current

      // Удалить все ордеры и сделки с графика
      ac.getAllShapes().forEach(({ id }) => ac.removeEntity(id, { disableUndo: true }))
      Object.entries(ac.orders).forEach(([id, order]) => order.remove())

      ac.orders = {}
      ac.trades = []

      ac.setSymbol(symbol || "")
    }

    return () => {
      if (controllerRef.current) controllerRef.current.abort()
    }
  }, [account, symbol])

  // Выбрали новый order
  useEffect(() => {
    const ac = acRef.current

    if (!(ac && ac.dataReady())) {
      return
    }

    if (selectedOrder && selectedOrder.time) {
      if (selectedOrder.executions.length > 0) {  // есть сделки
        const execution = selectedOrder.executions[0]
        const id = ac.createShape(
          {
            time: execution.time
          }, {
          shape: 'vertical_line',
          overrides: { linecolor: "#058" },
          disableSelection: true,
        })
        if (selectionOnChart) {
          ac.removeEntity(selectionOnChart)
        }
        setSelectionOnChart(id)
      } else {
        if (selectionOnChart) {
          ac.removeEntity(selectionOnChart)
          setSelectionOnChart()
        }
      }
    } else {
      if (selectionOnChart) {
        ac.removeEntity(selectionOnChart)
        setSelectionOnChart()
      }
    }
  }, [selectedOrder])

  return html`
      <div className="orders_and_chart">
          <div id="tv_chart_container"></div>

              <table className="orders ${loading ? 'loading' : ''}">
                  <thead>
                  <tr>
                      <td><i>instrument</i></td>
                      <td><i>order_id</i></td>
                      <td><i>local_id</i></td>
                      <td><i>type</i></td>
                      <td><i>side</i></td>
                      <td><i>amount</i></td>
                      <td><i>filled</i></td>
                      <td><i>stop price</i></td>
                      <td><i>limit price</i></td>
                      <td><i>fill price</i></td>
                      <td><i>status</i></td>
                      <td><i>created</i></td>
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
  `
}


export default Orders
