const margin = {top: 0, right: 50, bottom: 0, left: 50};
const width = 1650 - margin.left - margin.right;
const height = 690 - margin.top - margin.bottom;

const parseDate = d3.timeParse('%Y-%m-%d %H:%M:%S');
const dateFormat = d3.timeFormat('%Y-%m-%d %H:%M');
const valueFormat = d3.format('+.2f');
const valueFormat2 = d3.format('+.2f');

const dim = {
  width: width + margin.left + margin.right, height: 900,
  margin: {top: 10, right: 50, bottom: 30, left: 50},
  ohlc: {height: height + 50},
  indicator: {height: 120, padding: 0}
};
dim.plot = {
  width: dim.width - dim.margin.left - dim.margin.right,
  height: dim.height - dim.margin.top - dim.margin.bottom
};
dim.indicator.top = dim.ohlc.height + dim.indicator.padding;
dim.indicator.bottom = dim.indicator.top + dim.indicator.height + dim.indicator.padding;

const indicatorTop = d3.scaleLinear()
  .range([dim.indicator.top, dim.indicator.bottom]);

const x = techan.scale.financetime().range([0, width]);
const x2 = techan.scale.financetime().range([0, width]);
// const y = d3.scaleLog().range([height, 0]);
const y = d3.scaleLinear().range([height, 0]);
const y_profit = d3.scaleLinear().range([height, 0]);

const candlestick = techan.plot.candlestick()
  .xScale(x)
  .yScale(y);

const ohlc = techan.plot.ohlc()
  .xScale(x)
  .yScale(y);

const tradearrow = techan.plot.tradearrow()
  .xScale(x)
  .yScale(y)
  .orient((d) => d.side.startsWith("buy") ? "up" : "down")
  .on("mouseenter", enter)
  .on("mouseout", out);

const xAxis = d3.axisBottom(x).ticks();  //.ticks(20).tickFormat("");
const xAxis1 = d3.axisBottom(x).ticks();

const yAxis = d3.axisLeft(y);
const yAxisProfit = d3.axisRight(y_profit);  // .tickFormat(d3.format(",.3s"));

const y2 = d3.scaleLinear().range([dim.indicator.bottom + dim.indicator.height, 0]);

const tickAnnotation = techan.plot.axisannotation()
  .axis(yAxis)
  .orient('left')
  .format(d3.format(',.2f'));

const profitAnnotation = techan.plot.axisannotation()
  .axis(yAxisProfit)
  .translate([width, 0])
  .orient('right')
  .width(42)
  .format(d3.format(',.1f'));

const timeAnnotation = techan.plot.axisannotation()
  .axis(xAxis)
  .orient('bottom')
  .format(dateFormat)
  .width(120)
  .height(15)
  .translate([0, height])

const crosshair = techan.plot.crosshair()
  .xScale(x)
  .yScale(y2)
  .xAnnotation(timeAnnotation)
  .yAnnotation([tickAnnotation, profitAnnotation])


const yLoadScale = d3.scaleLinear()
  .range([
    indicatorTop(0) + dim.indicator.height,
    indicatorTop(0) + 0,
  ]);

const yLoadAxis = d3.axisLeft(yLoadScale)
  .ticks(5)
  .tickFormat((v, i) => v);


const yDepositScale = d3.scaleLinear()
  .range([
    indicatorTop(0) + dim.indicator.height,
    indicatorTop(0) + 0,
  ]);

const yDrawdownScale = d3.scaleLinear()
  .range([
    indicatorTop(0) + 0,
    indicatorTop(0) + dim.indicator.height,
  ]);

// Индикатор Range Strength
const yIndScale = d3.scaleLinear()
  .range([
    indicatorTop(0) + dim.indicator.height - 20,
    indicatorTop(0) - 20,
  ]);

const yDepositAxis = d3.axisRight(yDepositScale)
  .ticks(5)
  .tickFormat((v, i) => v);


const svg = d3.select("body").append("svg")
  .attr("width", dim.width)
  .attr("height", dim.height)
  .append("g")
  .attr("transform", "translate(" + dim.margin.left + "," + dim.margin.top + ")");

const valueText = svg.append('text')
  .style("text-anchor", "start")
  .attr("class", "coords")
  .attr("transform", "translate(" + (width - 250) + "," + 15 + ")");

svg.append("clipPath")
  .attr("id", "clip")
  .append("rect")
  .attr("x", 0)
  .attr("y", y(1))
  .attr("width", width)
  .attr("height", y(0) - y(1));

// clip блока индикаторов справа и слева
svg.append("clipPath")
  .attr("id", "clip-macd")
  .append("rect")
  .attr("x", 0)
  .attr("y", 0)
  .attr("width", width)
  .attr("height", 2000);

svg.append("g")
  .attr("class", "main-grid")

const macd_svg = svg.append("g")
  .attr("class", "macd")
  .attr("clip-path", "url(#clip-macd)");

svg.append("g")
  .attr("class", "x axis")
  .attr("transform", "translate(0," + height + ")")
  .attr("clip-path", "url(#clip-macd)");

svg.append("g")
  .attr("class", "x-axis-2")
  .attr("transform", "translate(0," +
    (indicatorTop(0) + dim.indicator.height) + ")");

svg.append("g")
  .attr("class", "y-axis")

svg.append("g")
  .attr("class", "y-axis-deposit")
  .attr("transform", "translate(" +
    (dim.width - dim.margin.left - dim.margin.right) + ",0)");
svg.append("g")
  .attr("class", "y-axis-right")
  .attr("transform", "translate(" +
    (dim.width - dim.margin.left - dim.margin.right) + ",0)");
svg.append("g")
  .attr("class", "y-axis-ind")
  .attr("transform", "translate(" +
    (dim.width - dim.margin.left - dim.margin.right) + ",0)");
svg.append("g")
  .attr("class", "y-axis-load");

svg.append("g")
  .attr("class", "ohlc")
  .attr("clip-path", "url(#clip)");

svg.append("g")
  .attr("class", "candlestick")
  .attr("clip-path", "url(#clip)");

svg.append("g")
  .attr("class", "profit")
  .attr("clip-path", "url(#clip)");

svg.select('g.profit')
  .append("g")
  .attr("class", "profit_bg");

svg.select('g.profit')
  .append("g")
  .attr("class", "profit_line");

svg.select('g.profit')
  .append("g")
  .attr("class", "profit_line_cap");

const focus = svg.append("g")
  .attr("class", "focus");

focus.append('g')
  .attr("class", "crosshair")
  .call(crosshair);

svg.append("g")
  .attr("class", "tradearrow")
  .attr("clip-path", "url(#clip)");


async function run() {
  let data = await d3.csv('data.csv');
  let trades = await d3.csv('trades.csv');
  let stats = await d3.csv('stats.csv');
  let indicator = await d3.csv('data.csv');

  data = data.map((d) => ({
    date: parseDate(d.date),
    open: +d.open,
    high: +d.high,
    low: +d.low,
    close: +d.close,
    volume: 10
  }));

  trades = trades.map((d) => ({
    date: parseDate(d.date),
    side: d.side,
    type: d.side,
    price: d.price,
    profit: d.profit,
  }));

  let max_value = 0
  stats = stats.map(d => {
    const value = +d.net_value;
    max_value = Math.max(max_value, value);
    const drawdown = max_value - value;
    return {
      date: parseDate(d.date),
      value: +d.net_value,
      drawdown: drawdown,
      load: +d.margin_used,
    }
  });

  indicator = indicator.map((d) => { d.date = parseDate(d.date); return d });

  draw(data, trades, stats, indicator);
}


function draw(data, trades, stats, indicator) {
  let accessor = ohlc.accessor();

  data.sort((a, b) => (
    d3.ascending(accessor.d(a), accessor.d(b))
  ));

  console.log("data length:", data.length);
  // const bgn = 0;
  // const len = 450;
  // data = data.slice(bgn, bgn + len);

  x.domain(data.map(accessor.d));
  let dom = techan.scale.plot.ohlc(data, accessor).domain();
  y.domain([dom[0] - (dom[1] - dom[0]) / 5, dom[1]]).nice();

  const max_pl = d3.max(trades, (d) => Math.abs(+d.profit));
  y_profit.domain([0, Math.max(160, max_pl)]).nice();

  // // Вертикальные линии дней
  svg.select("g.main-grid")
    .call(
      d3.axisTop(x)
        .ticks(0)
        .tickFormat("")
    )
  // svg.select("g.main-grid")
  //   .call(
  //     d3.axisTop(x)
  //       .ticks(width)
  //       .tickSize(-height)
  //       .tickFormat("")
  //   )
  // // Отметить начало новой недели
  // const ticks = d3.selectAll(".tick line");
  // const ticks_data = ticks.data();
  // ticks.attr("class", function(d, i){
  //   const prev_d = ticks_data[i > 0 ? i - 1 : 0];
  //   if (d.getDay() < prev_d.getDay() || d.getMonth() !== prev_d.getMonth()) {
  //     return "new_week";
  //   }
  // });


  svg.select('g.candlestick')
    .datum(data)
    // .call(ohlc)
    .call(candlestick)

  // Net Value gridlines
  svg.select("g.macd-grid")
    .call(
      d3.axisLeft(y).ticks(0).tickSize(-width).tickFormat("")
    )

  // ATR TRAILING STOP
  // const atrtrailingstopData = techan.indicator.atrtrailingstop()(data);
  // svg.selectAll("g.atrtrailingstop").datum(atrtrailingstopData).call(atrtrailingstop);

  // СТРЕЛКИ
  svg.select("g.tradearrow")
    .datum(trades)
    .call(tradearrow);

  // ФОН ГРИБОЧКОВ
  svg.select('g.profit_bg')
    .selectAll("rect")
    .data(trades)
    .enter()
    .append("rect")
      .attr("x", (d, i) => {
        let prev_d = trades[i > 0 ? i - 1 : 0];
        return x(prev_d.date);
      })
      .attr("width", (d, i) => {
        let prev_d = trades[i > 0 ? i - 1 : 0];
        return x(d.date) - x(prev_d.date);
      })
      .attr("height", d => y_profit(0) )
      .attr("y", 0 )
      .style("fill", d => {
        if (d.profit < -30) {
          return "rgba(220,0,50,0.05)"
        } else if (d.profit < -5) {
          return "rgba(200,150,0,0.05)"
        } else if (d.profit > 5) {
          // return "none"
          return "rgba(0,150,0,0.08)"
        } else {
          return "none"
        }
      });

  // ЛИНИИ ГРИБОЧКОВ
  svg.select('g.profit_line')
    .selectAll("line")
    .data(trades)
    .enter()
    .append("line")
      .attr("x1", d => x(d.date))
      .attr("x2", d => x(d.date))
      .attr("y1", d => y_profit(Math.abs(d.profit)))
      .attr("y2", y_profit(0))
      .attr("stroke-width", 0.8)
      .attr("stroke", d => d.profit < 0 ? "#d00" : "#080")

  // ШАПКИ ГРИБОЧКОВ
  svg.select('g.profit_line_cap')
    .selectAll("circle")
    .data(trades)
    .enter()
    .append("circle")
      .attr("cx", d => x(d.date))
      .attr("cy", d => y_profit(Math.abs(d.profit)))
      .attr("r", d => Math.abs(d.profit) === max_pl ? 5 : 2.5)
      .attr("fill", d => {
        if (Math.abs(d.profit) > 2) {
          return d.profit < 0 ? "#d00" : "#080";
        } else {
          return "#999";
        }
      })
      .attr("stroke-width", 0.5)
      .attr("stroke", "white")


  // Profit, drawdown, margin usage
  const min_deposit = d3.min(stats, d => d.value);
  const max_deposit = d3.max(stats, d => d.value);
  yDepositScale.domain([min_deposit, max_deposit]);
  macd_svg.append("path")
    .datum(stats)
    .attr("class", "deposit")
    .attr("d", d3.area()
      .curve(d3.curveStepAfter)
      .x(d => x(d.date))
      .y0(yDepositScale(min_deposit))
      .y1(d => yDepositScale(d.value))
    );
  yDrawdownScale.domain([0, max_deposit-min_deposit]);
  macd_svg.append("path")
    .datum(stats)
    .attr("class", "drawdown")
    .attr("d", d3.area()
      .curve(d3.curveStepAfter)
      .x(d => x(d.date))
      .y0(yDrawdownScale(0))
      .y1(d => yDrawdownScale(d.drawdown))
    );

  yLoadScale.domain([0, d3.max(stats, d => +d.load)]).nice();
  macd_svg.append("path")
    .datum(stats)
    .attr("class", "load")
    .attr("d", d3.line()
      .curve(d3.curveStepAfter)
      .x(d => x(d.date))
      .y(d => yLoadScale(d.load))
    );
  macd_svg.append("g")
    .attr("class", "macd-grid")
    .call(d3.axisLeft(yLoadScale).ticks(5).tickSize(-width).tickFormat(""))



  // Индикаторы на графике цены
  // svg.select('g.candlestick').append("path")
  //   .datum(indicator)
  //   .attr("class", "indicator-bottom line")
  //   .attr("clip-path", "url(#clip)")
  //   .attr("d", d3.line()
  //     .x(d => x(d.date))
  //     .y(d => y(+d.up))
  //     .defined(d => +d.up && (d.trend === undefined || d.trend > 0))
  //   );

  // svg.select('g.candlestick').append("path")
  //   .datum(indicator)
  //   .attr("class", "indicator-mid line")
  //   .attr("clip-path", "url(#clip)")
  //   .attr("d", d3.line().x(d => x(d.date)).y(d => y(+d.trend + 21)));

  // svg.select('g.candlestick').append("path")
  //   .datum(indicator)
  //   .attr("class", "indicator-top line")
  //   .attr("clip-path", "url(#clip)")
  //   .attr("d", d3.line()
  //     .x(d => x(d.date))
  //     .y(d => y(+d.dn))
  //     .defined(d => +d.dn && (d.trend === undefined || d.trend < 0))
  //   );

  // // Линии стоп-сигнала
  // svg.select('g.candlestick').append("path")
  //   .datum(indicator)
  //   .attr("class", "indicator-stop line")
  //   .attr("clip-path", "url(#clip)")
  //   .attr("d", d3.line().x(d => x(d.date)).y(d => y(d.min_win)));
  // svg.select('g.candlestick').append("path")
  //   .datum(indicator)
  //   .attr("class", "indicator-stop line")
  //   .attr("clip-path", "url(#clip)")
  //   .attr("d", d3.line().x(d => x(d.date)).y(d => y(d.max_win)));



  //
  // // Индикатор, разрешающий торговлю
  // // масштаб
  // // atr, sar, kama
  // const ind_field = "ind";
  // let min = d3.min(indicator, d => +d[ind_field]);
  // let max = d3.max(indicator, d => +d[ind_field]);
  // let range = Math.max(Math.abs(min), Math.abs(max));
  // // yIndScale.domain([
  // //   d3.min(indicator, d => +d[ind_field]),
  // //   d3.max(indicator, d => +d[ind_field]),
  // // ]);
  // yIndScale.domain([-range, range]).nice();
  // // ЛИНИЯ ИНДИКАТОРА
  // // macd_svg.append("path")
  // //   .datum(indicator)
  // //   .attr("class", "ind line")
  // //   .attr("d", d3.line()
  // //     .x(d => x(d.date))
  // //     .y(d => yIndScale(d[ind_field]))
  // //   );
  //
  // // БАРЫ ИНДИКАТОРА
  // const x_band = d3.scaleBand()
  //   .range([0, width])
  //   .padding(0.5);
  // x_band.domain(data.map(accessor.d));
  // const zero_y = yIndScale(0);
  // // macd_svg.selectAll(".bar")
  // //   .data(indicator)
  // //   .enter().append("rect")
  // //     .attr("x", d => x_band(d.date))
  // //     .attr("width", x_band.bandwidth() * 3)
  // //     .attr("y", d => {
  // //       if (d[ind_field] > 0) {
  // //         return yIndScale(d[ind_field]);
  // //       } else {
  // //         return zero_y;
  // //       }
  // //     })
  // //     .attr("height", d => Math.abs(zero_y - yIndScale(d[ind_field])))
  // //     .attr("fill", d => (d[ind_field] > 0 ? "#00aa00" : "red"))
  // // линия 0
  // macd_svg.append("g")
  //   .attr("class", "ind_grid")
  //   .call(d3.axisLeft(yIndScale).ticks(1).tickSize(-width).tickFormat(""))

  // Indicator on main chart
  // svg.select('g.candlestick').selectAll("dot")
  //   .data(indicator)
  //   .enter()
  //   .append("circle")
  //   .attr("cx", d => x(d.date))
  //   .attr("cy", d => y(d.kama))
  //   .attr("r", 1)
  //   .attr("fill", "#000")

  // // Drawdown gridlines
  // svg.append("g")
  //   .attr("class", "macd-grid")
  //   .call(
  //     d3.axisLeft(yDrawdownScale).ticks(5).tickSize(-width).tickFormat("")
  //   )

  // Net Value gridlines
  macd_svg.append("g")
    .attr("class", "macd-grid")
    .call(
      d3.axisLeft(yDepositScale).ticks(5).tickSize(-width).tickFormat("")
    )

  svg.selectAll("g.x.axis").call(xAxis);
  svg.selectAll("g.x-axis-2").call(xAxis1);

  svg.selectAll("g.y-axis").call(yAxis);
  svg.selectAll("g.y-axis-right").call(yAxisProfit);
  svg.selectAll("g.y-axis-deposit").call(yDepositAxis);
  svg.selectAll("g.y-axis-load").call(yLoadAxis);


  const extent = [[0, 0], [width, height]];
  const defaultSelection = [x.range()[0], x.range()[1]];

  const zoom = d3.zoom()
    .scaleExtent([1, 8])
    .translateExtent(extent)
    .extent(extent)
    .on("zoom", zoomed);

  const brush = d3.brushX()
    .extent([[0, dim.indicator.top], [width, dim.indicator.top + dim.indicator.height]])
    .on("brush", brushed);

  function brushed() {
    if (d3.event.sourceEvent && d3.event.sourceEvent.type === "zoom") return;
    let selection = d3.event.selection;
    if (selection) {
      svg.call(zoom.transform, d3.zoomIdentity
        .scale(width / (selection[1] - selection[0]))
        .translate(-selection[0], 0));
    }
  }

  svg.call(brush)
    .call(brush.move, defaultSelection);

  svg.call(zoom);

  function zoomed() {
    let t = d3.event.transform;

    // Зум оси X
    x.range([0, width].map(d => t.applyX(d)));

    // Двигаю brush в положение, соответствующее зуму
    svg.call(brush.move, x2.range().map(t.invertX, t));

    // console.log("zoom", [0, width].map(x.invert, x))

    svg.select('g.candlestick')
      .datum(data)
      // .call(ohlc)
      .call(candlestick)

    // СТРЕЛКИ
    svg.select("g.tradearrow")
      .datum(trades)
      .call(tradearrow);

    // ФОН ГРИБОЧКОВ
    svg.select('g.profit_bg')
      .selectAll("rect")
      .attr("x", (d, i) => {
        let prev_d = trades[i > 0 ? i - 1 : 0];
        return x(prev_d.date);
      })
      .attr("width", (d, i) => {
        let prev_d = trades[i > 0 ? i - 1 : 0];
        return x(d.date) - x(prev_d.date);
      });

    // ЛИНИИ ГРИБОЧКОВ
    svg.select('g.profit_line')
      .selectAll("line")
        .attr("x1", d => x(d.date))
        .attr("x2", d => x(d.date));

    // ШАПКИ ГРИБОЧКОВ
    svg.select('g.profit_line_cap')
      .selectAll("circle")
        .attr("cx", d => x(d.date));

    let din_cnt = x() / 100;
    let xAxisZ = d3.axisBottom(x).ticks(din_cnt);

    svg.select("g.main-grid")
      .call(
        d3.axisTop(x)
          .ticks(din_cnt)
          .tickSize(-height)
          .tickFormat("")
      )

    svg.selectAll("g.x.axis").call(xAxisZ);
  }
}


function enter(d) {
  valueText.style("display", "block");
  refreshText(d);
}

function out() {
  valueText.style("display", "none");
}

function refreshText(d) {
  valueText.html(
    "<tspan x='0' dy='1.5em'>" + dateFormat(d.date) + "</tspan>" +
    "<tspan x='0' dy='1.5em'>" +
    d.side + " " + valueFormat(d.price) + " " + valueFormat2(d.profit) +
    "</tspan>"
  );
  // valueText.attr("transform", "translate(" + x(d.date) + ")");
}

function toggleTrades(el) {
  let tradearrow_layer = svg.select("g.tradearrow");
  let current_state = tradearrow_layer.style("display") !== "none";
  if (current_state) {
    tradearrow_layer.style("display", "none")
  } else {
    tradearrow_layer.style("display", "block")
  }
}

run();

var span = document.createElement('span');
span.setAttribute('class', 'button');
span.setAttribute('onclick', 'toggleTrades()');
span.innerHTML = 'Show/Hide Trades';
document.getElementById("buttons").append(span);
