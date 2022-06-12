import {React, html, useEffect, useState} from "./deps.js";


const draw_order = function (ac, order) {
  let color;
  let icon_shape;
  let size;

  let price = parseFloat(order["price"]);

  if (order["side"] === "buy") {
    color = "#080";
    icon_shape = "0xf0d8";
    size = 30;
  } else if (order["side"] === "sell") {
    color = "#d00";
    icon_shape = "0xf0d7";
    size = 30;
  } else {
    color = "#49d";
    icon_shape = "0xf00d";
    size = 20;
  }

  const arrow_bg = ac.createShape(
    {time: order["time"], price: price},
    {
      shape: 'icon',
      overrides: {color: "#fff", size: size + 5, scale: 1},
      icon: icon_shape,
      zOrder: "top",
      disableSelection: true,
    }
  );
  const arrow = ac.createShape(
    {time: order["time"], price: price},
    {
      shape: 'icon',
      overrides: {color: color, size: size, scale: 1},
      icon: icon_shape,
      zOrder: "top",
      disableSelection: true,
    }
  );
}


const indicators = (PineJS) => {
  var myIndicator2 = {
    name: "aasdf",
    metainfo: {
      _metainfoVersion: 42,
      id: "FFFFF@tv-basicstudies-1",
      name: "111",
      description: "FFFFF",
      shortDescription: "Полоски",
      scriptIdPart: "",
      is_price_study: true,
      is_hidden_study: true,
      isCustomIndicator: true,
      isTVScript: false,
      isTVScriptStub: false,
      plots: [
        {'id': 'plot_0', 'type': 'line'},
        {'id': 'plot_1', 'type': 'line'},
      ],
      defaults: {
        styles: {
          plot_0: {
            linestyle: 0,
            visible: true,
            linewidth: 1,
            plottype: 2,
            trackPrice: false,
            transparency: 30,
            color: '#080'
          },
          plot_1: {
            linestyle: 0,
            visible: true,
            linewidth: 1,
            plottype: 2,
            trackPrice: false,
            transparency: 30,
            color: '#d00'
          },
        },
        precision: 2,
        inputs: {}
      },
      inputs: [],
    },
    constructor: function () {

      this.init = function (context, inputCallback) {
        this._context = context;
        this._input = inputCallback;

        var symbol = PineJS.Std.ticker(this._context) + "#indicator";
        this._context.new_sym(symbol, PineJS.Std.period(this._context), PineJS.Std.period(this._context));
      };

      this.main = function (context, inputCallback) {
        this._context = context;
        this._input = inputCallback;

        this._context.select_sym(1);

        var up = PineJS.Std.open(this._context);
        var dn = PineJS.Std.close(this._context);

        return [up, dn];
      }
    }
  };

  return Promise.resolve([myIndicator2]);
}


const create_chart = (el) => {
  // noinspection JSPotentiallyInvalidConstructorUsage
  window.tv = new TradingView.widget({
    debug: false,
    fullscreen: false,
    symbol: "A",
    interval: "1",
    container: el,
    datafeed: new Datafeeds.UDFCompatibleDatafeed("/bt"),
    library_path: "/static/admin/js/charting_library/",
    locale: "en",
    disabled_features: [
      "symbol_search_hot_key",
      "symbol_search",
      "left_toolbar",
      "control_bar",
      "edit_buttons_in_legend",
      // "header_widget",
      "pane_context_menu",
      "scales_context_menu",
      "legend_context_menu",
      "timeframes_toolbar",
      "right_bar_stays_on_scroll",
    ],
    width: "100%",
    height: "500px",
    toolbar_bg: '#f4f7f9',
    custom_indicators_getter: indicators,
  });
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
      // console.log("DRAW", order)
      draw_order(ac, order);
    }
  }
}


const Orders = ({curResult, curStrategy}) => {
  const [orders, setOrders] = useState([]);

  const [dataLoaded, setDataLoaded] = useState();
  const [chart, setChart] = useState(null);

  const [resized, setResized] = useState(false);

  // Создание графика при старте
  useEffect(() => {

    console.error("create a chart");
    create_chart("tv_chart_container");

    window.tv.onChartReady(() => {
      console.log("onChartReady");

      const ac = window.tv.chart();
      const ser = ac.getSeries();

      // индикаторы
      ac.createStudy('FFFFF', false, true);
      // ac.createStudy('Colorer', false, false);

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

      setChart(ac);
    });

  }, []);

  // Изменились ордеры или прогрузился очередной кусок графика
  useEffect(() => {

    if (dataLoaded && !resized) {
      console.warn("first time");
      const ac = chart;
      const to = ac.getVisibleRange().to;
      ac.setVisibleRange(
        {from: to - 3600 * 24 * 6, to: to},
        {applyDefaultRightMargin: true}
      );
      setResized(true);
    }

    if (dataLoaded) {
      draw_orders(orders);
    } else {
      console.warn("No chart");
    }
  }, [orders, dataLoaded])

  const fetchOrders = (curResult, curStrategy) => {
    fetch(`/bt/events?result=${curResult}&strategy=${curStrategy}`)
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

  // // Изменился symbol
  useEffect(() => {
    // console.log("on result or strategy change", curResult, curStrategy)
    const chartDiv = document.getElementById("tv_chart_container");

    if (curResult && curStrategy && chart) {

      console.log("show chart", curResult, curStrategy);

      const chart_id = curResult + "_" + curStrategy

      // Показать график и выставить новый символ
      // удалить всё с графика
      chart.getAllShapes().forEach(({id, name}) => chart.removeEntity(id));
      chart.setSymbol(chart_id);
      chartDiv.style.display = 'block';
      // Дернуть перерисовку ордеров
      if (chart && dataLoaded) {
        draw_orders(orders);
      }
      fetchOrders(curResult, curStrategy);
    } else {
      // Скрыть график
      chartDiv.style.display = 'none';
    }
  }, [curStrategy, chart]);

  return html`
      <div className="orders_and_chart">
          <div id="tv_chart_container"></div>
      </div>
  `;
}


export default Orders;
