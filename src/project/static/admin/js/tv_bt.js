function initOnReady() {
  var widget = window.tv = new TradingView.widget({
    debug: false,
    fullscreen: false,
    symbol: 'COPX.ARCA',
    interval: '1',
    container: "tv_chart_container",

    datafeed: new Datafeeds.UDFCompatibleDatafeed("http://127.0.0.1:8000/bt"),
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
    height: "600px",


    custom_indicators_getter: function (PineJS) {

      var myIndicator = {
        name: "Deposit And Drawdown",
        metainfo: {
          _metainfoVersion: 42,

          id: "BarColoring@tv-basicstudies-1",

          name: "BarColoring",
          description: "DepositAndDrawdown",
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
                linewidth: 1,       // plot line width.
                plottype: 4,       /* plot type
                          1  Histogram
                          2  Line
                          3  Cross
                          4  Area
                          5  Columns
                          6  Circles
                          7  Line with Breaks
                          8  Area with Breaks */
                trackPrice: false,   // show price line?
                transparency: 70,      // plot transparency, in percent.
                color: '#2e96d9' // plot color in #RRGGBB format
              },
              plot_1: {
                linestyle: 0,
                visible: true,
                linewidth: 1,      // plot line width.
                plottype: 4,       /* plot type
                          1  Histogram
                          2  Line
                          3  Cross
                          4  Area
                          5  Columns
                          6  Circles
                          7  Line with Breaks
                          8  Area with Breaks */
                trackPrice: false,   // show price line?
                transparency: 80,      // plot transparency, in percent.
                color: '#ff2600' // plot color in #RRGGBB format
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
              histogramBase: 500,
            }
          },
          inputs: [],

        },
        constructor: function () {

          this.main = function (context, inputCallback) {
            this._context = context;
            this._input = inputCallback;

            var result = PineJS.Std.high(this._context) + 1 - 23;
            var result1 = PineJS.Std.high(this._context) - 3 - 23;

            var time = PineJS.Std.time(this._context) / 1000;
            // console.log(time);

            // result1 = (time - 1645633200) / 1000000;

            var result3 = 0;
            for (const order of window.orders) {
              // console.log(order["time"], time)
              if (Math.round(order["time"] / 100) < Math.round(time / 100)) {
                result3 = order.amount - 500;
              }
            }

            return [result3, 500 - result3/5];
          }
        }
      };


      var myIndicator2 = {
        name: "aasdf",
        metainfo: {
          _metainfoVersion: 42,
          id: "FFFFF@tv-basicstudies-1",
          name: "111",
          description: "FFFFF",
          shortDescription: "2222",
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
                linewidth: 2,
                plottype: 2,
                trackPrice: false,
                transparency: 30,
                color: '#080'
              },
              plot_1: {
                linestyle: 0,
                visible: true,
                linewidth: 2,
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

            var symbol = 'indicator';
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



      var myIndicator5 = {
        name: "aasdf",
        metainfo: {
          _metainfoVersion: 42,
          id: "dddFFF@tv-basicstudies-1",
          name: "111",
          description: "PROFIT",
          shortDescription: "2222",
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
                linewidth: 2,
                plottype: 8,
                trackPrice: false,
                transparency: 60,
                color: '#08d'
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
            this._context.new_sym('profit', PineJS.Std.period(this._context), PineJS.Std.period(this._context));
          };

          this.main = function (context, inputCallback) {
            this._context = context;
            this._input = inputCallback;
            this._context.select_sym(1);
            var profit = PineJS.Std.open(this._context);
            return [profit];
          }
        }
      };



        var ColorerIndicator = {
          name: "asdfas",
          metainfo: {
              _metainfoVersion: 22,

              id: "Colorer@tv-basicstudies-1",

              name: "Colorer",
              description: "Colorer",
              shortDescription: "Colorer",
              scriptIdPart: "",
              is_price_study: true,
              is_hidden_study: false,
              isCustomIndicator: true,

              isTVScript: false,
              isTVScriptStub: false,
              defaults: {
                  precision: 4,
                  palettes: {
                      palette_0: {
                          colors: [
                              { color: "#ffffff" },
                              { color: "#fdf0d9" }
                          ]
                      }
                  }
              },
              inputs: [],
              plots: [{
                  id: "plot_0",

                  // plot type should be set to 'bar_colorer'
                  type: "bg_colorer",

                  // this is the name of the palette that is defined
                  // in 'palettes' and 'defaults.palettes' sections
                  palette: "palette_0"
              }],
              palettes: {
                  palette_0: {
                      colors: [
                          { name: "Color 0" },
                          { name: "Color 1" }
                      ],

                      // the mapping between the values that
                      // are returned by the script and palette colors
                      valToIndex: {
                          100: 0,
                          200: 1
                      }
                  }
              }
          },
          constructor: function() {
              this.main = function(context, input) {
                  this._context = context;
                  this._input = input;

                  var valueForColor0 = 100;
                  var valueForColor1 = 200;

                  var v = PineJS.Std.volume(this._context);
                  var result = v > 0 ? valueForColor0 : valueForColor1;

                  return [result];
              }
          }
      };

      return Promise.resolve([myIndicator, myIndicator2, ColorerIndicator, myIndicator5]);
    },

  });

  const draw_order = function(ac, order) {
      let color;
      let icon_shape;
      let arrow_pos;

      let price = parseFloat(order["price"]);

      if (order["side"] === "buy") {
        color = "#080";
        icon_shape = "0xf176";
        arrow_pos = price * 0.995;
      } else if (order["side"] === "sell") {
        color = "#d00";
        icon_shape = "0xf175";
        arrow_pos = price * 1.005;
      } else {
        color = "#000";
        icon_shape = "0xf175";
        arrow_pos = null;
      }

      // const level = ac.createShape(
      //   { time: order["time"], price: price },
      //   {
      //     shape: 'arrow_right',
      //     overrides: {color: color, fontsize: 14 },
      //     zOrder: "top",
      //     disableSelection: true,
      //     lock: true,
      //     text: order["price"]
      //   }
      // );

      if (arrow_pos) {
        const arrow = ac.createShape(
          {time: order["time"], price: arrow_pos},
          {
            shape: 'icon',
            overrides: {color: color, size: 20, scale: 1.1},
            icon: icon_shape,
            zOrder: "top",
            disableSelection: true,
          }
        );
      }

      const icon_bg = ac.createShape(
        { time: order["time"], price: price },
        {
          shape: 'icon',
          overrides: {color: "#fff", size: 15, scale: 1},
          icon: '0xf111',
          zOrder: "top",
          disableSelection: true,
        }
      );
      const icon = ac.createShape(
        { time: order["time"], price: price },
        {
          shape: 'icon',
          overrides: {color: color, size: 8, scale: 1},
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
    // widget.activeChart().createStudy('DepositAndDrawdown', false, true);
    widget.activeChart().createStudy('FFFFF', false, true);
    // widget.activeChart().createStudy('PROFIT', false, true);
    widget.activeChart().createStudy('Colorer', false, false);

    const ac = widget.chart();
    const ser = ac.getSeries();

    ac.applyOverrides({"mainSeriesProperties.showPriceLine": false})
    ac.applyOverrides({"paneProperties.topMargin": '2'})
    ac.applyOverrides({"paneProperties.bottomMargin": '2'})

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


  });

}

window.addEventListener('DOMContentLoaded', initOnReady, false);

