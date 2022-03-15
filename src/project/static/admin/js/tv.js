function initOnReady() {
  var widget = window.tv = new TradingView.widget({
    debug: false,
    fullscreen: false,
    symbol: 'URA.ARCA',
    interval: '15',
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
      //"volume_force_overlay",
      "create_volume_indicator_by_default",

      //"header_symbol_search",
      //"header_resolutions",
      //"header_chart_type",
      //"header_settings",
      /////"header_indicators",
      "header_compare",
      "header_undo_redo",
      "header_screenshot",
      //"header_fullscreen_button",
      "header_saveload",
      //"header_widget",

      "pane_context_menu",
      "scales_context_menu",
      "legend_context_menu",

      "legend_widget",
    ],
    enabled_features: [
      "timeframes_toolbar",
      //"move_logo_to_main_pane",
    ],
    client_id: 'trading_platform_demo',
    user_id: 'public_user',
    theme: "light",
    timezone: "Etc/UTC",

    enable_publishing: false,
    allow_symbol_change: true,
    width: '100%',
    height: '800px',

    custom_indicators_getter: function (PineJS) {

      var myIndicator = {
        name: "Bar Colorer Demo",
        metainfo: {
          _metainfoVersion: 42,

          id: "BarColoring@tv-basicstudies-1",

          name: "BarColoring",
          description: "Bar Colorer Demo",
          shortDescription: "BarColoring",
          scriptIdPart: "",
          is_price_study: false,
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
                linewidth: 2,       // plot line width.
                plottype: 3,       /* plot type
                          1  Histogram
                          2  Line
                          3  Cross
                          4  Area
                          5  Columns
                          6  Circles
                          7  Line with Breaks
                          8  Area with Breaks */
                trackPrice: false,   // show price line?
                transparency: 30,      // plot transparency, in percent.
                color: '#ff5500' // plot color in #RRGGBB format
              },
              plot_1: {
                linestyle: 0,
                visible: true,
                linewidth: 1,      // plot line width.
                plottype: 1,       /* plot type
                          1  Histogram
                          2  Line
                          3  Cross
                          4  Area
                          5  Columns
                          6  Circles
                          7  Line with Breaks
                          8  Area with Breaks */
                trackPrice: false,   // show price line?
                transparency: 30,      // plot transparency, in percent.
                color: '#88aa55' // plot color in #RRGGBB format
              }
            },
            precision: 2,
            inputs: {}
          },
          styles: {
            plot_0: {
              title: 'aaaa',
              histogramBase: 0,
            },
            plot_1: {
              title: 'bbbb',
              histogramBase: 0,
            }
          },
          inputs: [],

        },
        constructor: function () {

          this.main = function (context, inputCallback) {
            this._context = context;
            this._input = inputCallback;

            var result = PineJS.Std.high(this._context) + 1 - 170;
            var result1 = PineJS.Std.high(this._context) - 3 - 170;

            var time = PineJS.Std.time(this._context);

            return [result, result1];
          }
        }
      };


      var myIndicator2 = {
        name: "FFFFF",
        metainfo: {
          _metainfoVersion: 42,

          id: "FFFFF@tv-basicstudies-1",

          name: "FFFFF",
          description: "FFFFF",
          shortDescription: "FFFFF",
          scriptIdPart: "",
          is_price_study: false,
          is_hidden_study: true,
          isCustomIndicator: true,

          isTVScript: false,
          isTVScriptStub: false,

          plots: [
            {'id': 'plot_0', 'type': 'line'},
          ],
          defaults: {
            styles: {
              plot_0: {
                linestyle: 0,
                visible: true,
                linewidth: 2,       // plot line width.
                plottype: 2,       /* plot type
                          1  Histogram
                          2  Line
                          3  Cross
                          4  Area
                          5  Columns
                          6  Circles
                          7  Line with Breaks
                          8  Area with Breaks */
                trackPrice: false,   // show price line?
                transparency: 30,      // plot transparency, in percent.
                color: '#06f' // plot color in #RRGGBB format
              },
            },
            precision: 2,
            inputs: {}
          },
          styles: {
            plot_0: {
              title: 'aaaa',
              histogramBase: 0,
            },
          },
          inputs: [],

        },
        constructor: function () {

          this.init = function (context, inputCallback) {
            this._context = context;
            this._input = inputCallback;

            var symbol = 'MNTS'; //PineJS.Std.ticker(this._context) + "#TEST";
            this._context.new_sym(symbol, PineJS.Std.period(this._context), PineJS.Std.period(this._context));
          };

          this.main = function (context, inputCallback) {
            this._context = context;
            this._input = inputCallback;

            this._context.select_sym(1);

            var v = 10 - PineJS.Std.close(this._context);
            return [v];
          }
        }
      };

      return Promise.resolve([myIndicator, myIndicator2]);
    },

  });

  const draw_order = function(ac, order) {
      let color;
      let icon_shape;
      let arrow_pos;
      if (order["side"] === "buy") {
        color = "#080";
        icon_shape = "0xf176";
        arrow_pos = order["price"] * 0.995;
      } else {
        color = "#d00";
        icon_shape = "0xf175";
        arrow_pos = order["price"] * 1.005;
      }

      // const level = ac.createShape(
      //   { time: order["time"], price: order["price"] },
      //   {
      //     shape: 'arrow_right',
      //     overrides: {color: color, fontsize: 14 },
      //     zOrder: "top",
      //     disableSelection: true,
      //     lock: true,
      //     text: order["dt"]
      //   }
      // );

      const arrow = ac.createShape(
        { time: order["time"], price: arrow_pos },
        {
          shape: 'icon',
          overrides: {color: color, size: 17, scale: 1.1},
          icon: icon_shape,
          zOrder: "top",
          disableSelection: true,
        }
      );
      const icon_bg = ac.createShape(
        { time: order["time"], price: order["price"] },
        {
          shape: 'icon',
          overrides: {color: "#fff", size: 12, scale: 1},
          icon: '0xf111',
          zOrder: "top",
          disableSelection: true,
        }
      );
      const icon = ac.createShape(
        { time: order["time"], price: order["price"] },
        {
          shape: 'icon',
          overrides: {color: color, size: 6, scale: 1},
          icon: '0xf111',
          zOrder: "top",
          disableSelection: true,
        }
      );
  }

  const draw_orders = function(ac) {
    const range = ac.getVisibleRange();
    for (const order of window.orders) {
      if (!order.visible && range.from < order["time"] && order["time"] < range.to) {
        draw_order(ac, order);
        order.visible = true;
      }
    }
  }

  widget.onChartReady(function () {
    // widget.chart().createStudy('Bar Colorer Demo', false, true);
    // widget.chart().createStudy('FFFFF', false, true);
    // widget.chart().createStudy('MACD', false, false);

    const ac = widget.chart();
    const ser = ac.getSeries();

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

    ac.onDataLoaded().subscribe(
        null,
        () => draw_orders(ac),
        false
    );



    // ac.createMultipointShape(
    //   [
    //     { time: 1645214400, price: 4340 },
    //     { time: 1645215000, price: 4350 }
    //   ],
    //   {
    //     shape: 'price_label',
    //     overrides: {backgroundColor: "#dd0000", color: "#dd0000" },
    //   }
    // );

    // ac.createShape({ time: 1645214400 }, { shape: 'arrow_marker' });  // ok
    // ac.createShape({ time: 1645215000 }, { shape: 'price_label' });
    // ac.createShape({ time: 1645215600 }, { shape: 'arrow', price: 4370, channel: "low", disableSelection: true });
    // ac.createShape({ time: 1645215600 }, { shape: 'price_note' });
    // ac.createShape({ time: 1645214400, price: 4370 }, { shape: 'callout' });
    // ac.createShape({ time: 1645215000, price: 4370 }, { shape: 'arrow_up', zOrder: "top", text: "asdf", overrides: {color: "#0f9" } });
    // ac.createShape({ time: 1645215600, price: 4370 }, { shape: 'icon', icon: '0xf068' });

    // widget.activeChart().createMultipointShape(
    //     [{ time: from, price: 150 }, { time: to, price: 150 }],
    //     {
    //         shape: "trend_line",
    //         lock: true,
    //         disableSelection: true,
    //         disableSave: true,
    //         disableUndo: true,
    //         text: "text",
    //     }
    // );

  });

}

window.addEventListener('DOMContentLoaded', initOnReady, false);

