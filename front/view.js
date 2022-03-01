const chart = document.getElementById("chart");
const buttons = document.getElementById("buttons");

const margin = {top: 0, right: 80, bottom: 0, left: 60};
const width = chart.clientWidth - margin.left - margin.right;
const height = chart.clientHeight - margin.top - margin.bottom - (120 + 100 + 50);

const parseDate = d3.timeParse('%Y-%m-%d %H:%M:%S');
const dateFormat = d3.timeFormat('%Y-%m-%d %H:%M');
const valueFormat = d3.format('+.2f');
const valueFormat2 = d3.format('+.2f');

const dim = {
  width: width + margin.left + margin.right,
  height: chart.clientHeight - buttons.clientHeight,
  margin: {top: 10, right: 80, bottom: 30, left: 60},
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
const y = d3.scaleLinear().range([height, 0]);
const y_profit = d3.scaleLinear().range([height, 0]);

const candlestick = techan.plot.candlestick()
  .xScale(x)
  .yScale(y);

const ohlc = techan.plot.ohlc()
  .xScale(x)
  .yScale(y);

const arrowOrient = techan.svg.arrow()
  .orient(d => d.side.startsWith("buy") ? "up" : "down")
  .x(d => x(d.date) - x.band() * 1.25)
  .y(d => y(d.price));

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
  .yScale(y)
  .xAnnotation([timeAnnotation])
  .yAnnotation([tickAnnotation, profitAnnotation])
  // .on("move", function (coords) { console.log(coords) });

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


const svg = d3.select("#chart").append("svg")
  .attr("width", dim.width)
  .attr("height", dim.height)
  .append("g")
  .attr("transform", "translate(" + dim.margin.left + "," + dim.margin.top + ")");

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
  .attr("clip-path", "url(#clip)");

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

svg.append("g")
  .attr("class", "tradearrow")
  .attr("clip-path", "url(#clip)");

const crosshair_svg = svg.append('g')
  .attr("class", "crosshair")
  .call(crosshair)

const macd = svg.append("g")
  .attr("class", "macd")
  .attr("clip-path", "url(#clip-macd)");

const macd_svg = macd.append("g")
  .attr("class", "drawings")

const macd_brush = macd.append("g")
  .attr("class", "brush")

async function run() {
  data = await d3.csv('data.csv');
  trades = await d3.csv('trades.csv');
  stats = await d3.csv('stats.csv');
  indicator = await d3.csv('data.csv');

  const symbols = {};

  data.map(d => {
    symbols[d.ticker] = 1;
    d.date = parseDate(d.date);
    // Распарсить ohlc в числа
    d.open = +d.open;
    d.high = +d.high;
    d.low = +d.low;
    d.close = +d.close;
    d.volume = +d.volume;
  });

  // Кнопки переключения инструмента
  let index = 0;
  for (const symbol of Object.keys(symbols).sort()) {
    index += 1;
    const span = document.createElement('span');
    span.setAttribute('class', 'button');
    span.setAttribute('data-symbol', symbol);
    span.setAttribute('onclick', 'toggleChart("' + symbol + '")');
    span.innerHTML = `${index}. ${symbol.split(".")[0]}`;
    document.getElementById("instruments").append(span);
  }

  trades.map(d => { d.date = parseDate(d.date); d.type = d.side });

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

  indicator.map(d => { d.date = parseDate(d.date) });

  // Врубить первый график
  if (symbols) {
    toggleChart(Object.keys(symbols).sort()[0]);
  }

  draw_stats(stats);
}


const toggleChart = function (symbol) {
  const buttons = document.querySelectorAll("#instruments span");
  buttons.forEach(node => {
    node.classList.remove('active');
    if (node.getAttribute("data-symbol") === symbol) {
      node.classList.add('active');
    }
  });

  // Очистить список сделок
  const $trades = document.querySelector('#trades');
  $trades.innerHTML = "";

  // Очистить график
  svg.selectAll('.profit g *').remove();
  svg.selectAll('.candlestick *').remove();
  svg.selectAll('.tradearrow *').remove();

  // Сбросить зум
  x.range([0, width]);

  // Отфильтровать данные, запустить draw
  const sym_data = data.filter(d => d.ticker === symbol);
  const sym_trades = trades.filter(d => d.symbol === symbol);
  draw(sym_data, sym_trades, sym_data);

  // Вывести количество SVG-элементов на странице
  const num = ["clipPath", "circle", "rect", "path", "text", "g", "line"]
    .map(tag => document.getElementsByTagName(tag).length)
    .reduce((res, length) => res + length);
  const svg_cnt = document.querySelector("#svg_cnt");
  svg_cnt.innerHTML = num.toString();
}


// // Линии индикатора
// const indicator_top = d3.line()
//   .curve(d3.curveNatural)
//   .x(d => x(d.date))
//   .y(d => y(+d.up))
//   .defined(d => +d.up && (d.trend === undefined || d.trend < 0))
// const indicator_bottom = d3.line()
//   .curve(d3.curveNatural)
//   .x(d => x(d.date))
//   .y(d => y(+d.dn))
//   .defined(d => +d.dn && (d.trend === undefined || d.trend > 0));


function draw_stats(stats) {
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
  // Margin usage gridlines
  macd_svg.append("g")
    .attr("class", "macd-grid")
    .call(d3.axisLeft(yLoadScale).ticks(5).tickSize(-width).tickFormat(""))
  // Net Value gridlines
  macd_svg.append("g")
    .attr("class", "macd-grid")
    .call(
      d3.axisLeft(yDepositScale).ticks(5).tickSize(-width).tickFormat("")
    )

  svg.selectAll("g.y-axis-right").call(yAxisProfit);
  svg.selectAll("g.y-axis-deposit").call(yDepositAxis);
  svg.selectAll("g.y-axis-load").call(yLoadAxis);

}


function draw(data, trades, indicator) {
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
  y.domain([dom[0], dom[1]]);

  const max_pl = d3.max(trades, (d) => Math.abs(+d.profit));
  y_profit.domain([0, Math.max(100, max_pl) * 1.05]).nice();

  svg.select('g.candlestick')
    .datum(data)
    .call(ohlc)
    // .call(candlestick)

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
      .attr("r", 2.5)
      .attr("fill", d => {
        if (Math.abs(d.profit) > 2) {
          return d.profit < 0 ? "#d00" : "#080";
        } else {
          return "#999";
        }
      })
      .attr("stroke-width", 0.5)
      .attr("stroke", "white")


  // Индикаторы на графике цены
  svg.select('g.candlestick').append("path")
    .datum(indicator)
    .attr("class", "indicator-bottom line")
    .attr("d", indicator_bottom);

  svg.select('g.candlestick').append("path")
    .datum(indicator)
    .attr("class", "indicator-top line")
    .attr("d", indicator_top);


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
  // svg.select('g.tradearrow')
  //   .selectAll("circle")
  //   .data(trades)
  //   .enter()
  //   .append("circle")
  //   .attr("cx", d => {
  //     return x(d.date) - x.band() * 1.25;
  //   })
  //   .attr("cy", d => y(d.price))
  //   .attr("r", 4)
  //   .attr("fill", d => d.side.startsWith("buy") ? "#080" : "#d00")
  //   .attr("stroke-width", 1)
  //   .attr("stroke", "white")

  svg.selectAll("g.tradearrow")
    .selectAll("path")
    .data(trades)
    .enter()
    .append("path")
    .attr("class", d => "tradearrow " + d.side)
    .attr("d", arrowOrient);

  // // Drawdown gridlines
  // svg.append("g")
  //   .attr("class", "macd-grid")
  //   .call(
  //     d3.axisLeft(yDrawdownScale).ticks(5).tickSize(-width).tickFormat("")
  //   )

  svg.selectAll("g.x.axis").call(xAxis);
  svg.selectAll("g.x-axis-2").call(xAxis1);

  svg.selectAll("g.y-axis").call(yAxis);

  const extent = [[0, 0], [width, height]];
  const defaultSelection = [x.range()[0], x.range()[1]];

  const zoom = d3.zoom()
    .scaleExtent([1, 16])
    .translateExtent(extent)
    .extent(extent)
    .on("zoom", zoomed)
    .on("start", function () { svg.select(".scope-crosshair").attr("display", "none") })

  const brush = d3.brushX()
    .extent([[0, dim.indicator.top], [width, dim.indicator.top + dim.indicator.height]])
    .on("brush", brushed)

  function brushed() {
    if (d3.event.sourceEvent && d3.event.sourceEvent.type === "zoom") return;
    let selection = d3.event.selection;
    if (selection) {
      svg.call(zoom.transform, d3.zoomIdentity
        .scale(width / (selection[1] - selection[0]))
        .translate(-selection[0], 0));
    }
  }

  // Список всех сделок
  const $trades = document.querySelector('#trades');
  trades.slice(0).reverse().map(trade => {
    const tzoffset = (trade.date).getTimezoneOffset() * 60000;
    const utc_iso = (new Date(trade.date - tzoffset)).toISOString();
    const dt = utc_iso.slice(0, 16).replace("T", " ");
    const $trade = document.createElement('tr');
    let profit = "0";
    if (trade.profit > 0) {
      $trade.classList.add('gain');
      profit = "+" + parseFloat(trade.profit).toFixed();
    }
    if (trade.profit < 0) {
      $trade.classList.add('loss');
      profit = "−" + Math.abs(parseFloat(trade.profit)).toFixed();
    }
    $trade.classList.add('trade');

    const net_value = parseFloat(trade.net_value).toFixed();

    $trade.innerHTML += `<td class="date">${dt}</td>\n`;
    $trade.innerHTML += `<td class="side">${trade.side}</td>\n`;
    $trade.innerHTML += `<td class="profit">${profit}</td>\n`;
    $trade.innerHTML += `<td class="net_value">${net_value}</td>\n`;

    $trades.appendChild($trade);
  });

  macd_brush.call(brush).call(brush.move, defaultSelection);

  svg.call(zoom);

  function zoomed() {
    let t = d3.event.transform;

    // Зум оси X
    x.range([0, width].map(d => t.applyX(d)));
    // y.range([0, height].map(d => t.applyY(d)));

    // x.domain(data.map(accessor.d));
    // let dom = techan.scale.plot.ohlc(data, accessor).domain();
    // console.log(dom);
    // console.log(x.domain()[0]);
    // y.domain([dom[0] - (dom[1] - dom[0]) / 15, dom[1]]).nice();

    // Двигаю brush в положение, соответствующее зуму
    macd_brush.call(brush.move, x2.range().map(t.invertX, t));

    crosshair_svg.select(".scope-crosshair").attr("display", "none");

    // Новый диапазон
    // let new_range = [0, width].map(x.invert, x);
    // console.log("zoom", new_range[0], y_profit(1));

    svg.select('g.candlestick')
      .call(ohlc.refresh)
      // .call(candlestick.refresh)

    // Стрелки торгов
    svg.selectAll("g.tradearrow")
      .selectAll("path")
      .attr("d", arrowOrient);

    // ФОН ГРИБОЧКОВ
    svg.select('g.profit_bg')
      .selectAll("rect")
      .attr("x", (d, i) => {
        let prev_d = trades[i > 0 ? i - 1 : 0];
        return x(prev_d.date) - x.band() * 1.25;
      })
      .attr("width", (d, i) => {
        let prev_d = trades[i > 0 ? i - 1 : 0];
        return x(d.date) - x(prev_d.date);
      });

    // ЛИНИИ ГРИБОЧКОВ
    svg.select('g.profit_line')
      .selectAll("line")
        .attr("x1", d => x(d.date) - x.band() * 1.25)
        .attr("x2", d => x(d.date) - x.band() * 1.25);

    // ШАПКИ ГРИБОЧКОВ
    svg.select('g.profit_line_cap')
      .selectAll("circle")
        .attr("cx", d => x(d.date) - x.band() * 1.25);

    // Линии индикатора
    svg.select("g.candlestick .indicator-bottom")
      .attr("d", indicator_bottom);
    svg.select("g.candlestick .indicator-top")
      .attr("d", indicator_top);

    let din_cnt = (x.range()[1] - x.range()[0]) / 100;
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


function toggleTrades(el) {
  let tradearrow_layer = svg.select("g.tradearrow");
  let current_state = tradearrow_layer.style("display") !== "none";
  if (current_state) {
    tradearrow_layer.style("display", "none")
  } else {
    tradearrow_layer.style("display", "block")
  }
}
function toggleProfit(el) {
  let layer = svg.select("g.profit");
  let current_state = layer.style("display") !== "none";
  if (current_state) {
    layer.style("display", "none")
  } else {
    layer.style("display", "block")
  }
}

let data, trades, stats, indicator;

run();

let span;

span = document.createElement('span');
span.setAttribute('class', 'button');
span.setAttribute('onclick', 'toggleProfit()');
span.innerHTML = 'Profit';
document.getElementById("settings").append(span);

span = document.createElement('span');
span.setAttribute('class', 'button');
span.setAttribute('onclick', 'toggleTrades()');
span.innerHTML = 'Trades';
document.getElementById("settings").append(span);
