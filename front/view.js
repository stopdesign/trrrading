const margin = {top: 20, right: 50, bottom: 30, left: 50},
  width = 2000 - margin.left - margin.right,
  height = 750 - margin.top - margin.bottom;

const parseDate = d3.timeParse('%Y-%m-%d %H:%M:%S');
const dateFormat = d3.timeFormat('%Y-%m-%d %H:%M:%S');
const valueFormat = d3.format('+.2f');

const dim = {
  width: 2000, height: 1000,
  margin: {top: 20, right: 50, bottom: 30, left: 50},
  ohlc: {height: 750},
  indicator: {height: 100, padding: 0}
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
const y = d3.scaleLinear().range([height, 0]);

const candlestick = techan.plot.candlestick()
  .xScale(x)
  .yScale(y);

const ohlc = techan.plot.ohlc()
  .xScale(x)
  .yScale(y);

const tradearrow = techan.plot.tradearrow()
  .xScale(x)
  .yScale(y)
  .orient((d) => d.type.startsWith("buy") ? "up" : "down")
  .on("mouseenter", enter)
  .on("mouseout", out);

const xAxis = d3.axisBottom(x);
const xAxis1 = d3.axisBottom(x);

const yAxis = d3.axisLeft(y);

const yValueScale = d3.scaleLinear()
  .range([
    indicatorTop(0) + dim.indicator.height,
    indicatorTop(0)
  ]);

const yDrawdownScale = d3.scaleLinear()
  .range([
    indicatorTop(0) + dim.indicator.height,
    indicatorTop(0) + dim.indicator.height * 2
  ]);

const yValueAxis = d3.axisRight(yValueScale)
  .ticks(5)
  .tickFormat((v, i) => v);

const yDrawdownAxis = d3.axisRight(yDrawdownScale)
  .ticks(5)
  .tickFormat((v, i) => {
    if (v > 0) return v + "%"
  });

// define the line
const valueline1 = d3.area()
  .x(function (d) {
    return x(d.date);
  })
  .y0(yValueScale(0))
  .y1(function (d) {
    return yValueScale(d.value);
  })

// define the line
const valueline2 = d3.area()
  .x(function (d) {
    return x(d.date);
  })
  .y0(yDrawdownScale(0))
  .y1(function (d) {
    return yDrawdownScale(d.drawdown);
  })


const svg = d3.select("body").append("svg")
  .attr("width", dim.width)
  .attr("height", dim.height)
  .append("g")
  .attr("transform", "translate(" + dim.margin.left + "," + dim.margin.top + ")");
// .call(zoom);

const valueText = svg.append('text')
  .style("text-anchor", "end")
  .attr("class", "coords")
  .attr("x", width - 5)
  .attr("y", 15);

svg.append("clipPath")
  .attr("id", "clip")
  .append("rect")
  .attr("x", 0)
  .attr("y", y(1))
  .attr("width", width)
  .attr("height", y(0) - y(1));

svg.append("g")
  .attr("class", "candlestick")
  .attr("clip-path", "url(#clip)");

const macd_svg = svg.append("g").attr("class", "macd");

svg.append("g")
  .attr("class", "x axis")
  .attr("transform", "translate(0," + height + ")");

svg.append("g")
  .attr("class", "x-axis-2")
  .attr("transform", "translate(0," + dim.indicator.bottom + ")");

svg.append("g")
  .attr("class", "y axis")
  .append("text")
  .attr("transform", "rotate(-90)")
  .attr("y", 6)
  .attr("dy", ".71em")
  .style("text-anchor", "end")
  .text("Price ($)");

svg.append("g")
  .attr("class", "y-axis")
  .attr("transform", "translate(" +
    (dim.width - dim.margin.left - dim.margin.right) + ",0)");
svg.append("g")
  .attr("class", "y-axis-dd")
  .attr("transform", "translate(" +
    (dim.width - dim.margin.left - dim.margin.right) + ",0)");

svg.append("g")
  .attr("class", "ohlc");

svg.append("g")
  .attr("class", "tradearrow");

svg.append("g")
  .attr("class", "indicator");

svg.append("g")
  .attr("class", "y axis")
  .append("text")
  .attr("transform", "rotate(-90)")
  .attr("y", 6)
  .attr("dy", ".71em")
  .style("text-anchor", "end")
  .text("Price ($)");


async function run() {
  let data = await d3.csv('data.csv');
  let trades = await d3.csv('trades.csv');
  let stats = await d3.csv('stats.csv');
  let indicator = await d3.csv('indicator.csv');

  data = data.map((d) => ({
    date: parseDate(d.Date),
    open: +d.Open,
    high: +d.High,
    low: +d.Low,
    close: +d.Close,
    volume: 10
  }));

  trades = trades.map((d) => ({
    date: parseDate(d.Date),
    type: d.Direction,
    price: d.Price
  }));

  stats = stats.map((d) => ({
    date: parseDate(d.Date),
    value: d.Value,
    drawdown: d.Drawdown,
    RelEquity: d.RelEquity,
  }));

  indicator = indicator.map((d) => { d.date = parseDate(d.Date); return d });

  draw(data, trades, stats, indicator);
}

function draw(data, trades, stats, indicator) {
  let accessor = ohlc.accessor();

  data.sort((a, b) => (
    d3.ascending(accessor.d(a), accessor.d(b))
  ));

  // techanIntradayTimeInit = x.domain(data.map(accessor.d)).zoomable().copy();
  x.domain(data.map(accessor.d));
  y.domain(techan.scale.plot.ohlc(data, accessor).domain());

  svg.select('g.candlestick')
    .datum(data)
    .call(ohlc);

  svg.select("g.tradearrow")
    .datum(trades)
    .call(tradearrow);

  yValueScale.domain([
    d3.min(stats, (d) => +d.value),
    d3.max(stats, (d) => +d.value),
  ]); //.nice();

  yDrawdownScale.domain([0, d3.max(stats, (d) => +d.drawdown)]);
  // yDrawdownScale.domain([0, d3.max(stats, (d) => +d.RelEquity)]);

  macd_svg.append("path")
    .datum(stats)
    .attr("class", "signal")
    .attr("d", valueline1);

  macd_svg.append("path")
    .datum(stats)
    .attr("class", "drawdown")
    .attr("d", valueline2);

  // Rel Equity
  // macd_svg.append("path")
  //   .datum(stats)
  //   .attr("class", "drawdown")
  //   // .attr("d", valueline2);
  //   .attr("d", d3.area()
  //     .x(d => x(d.date))
  //     .y0(yDrawdownScale(0))
  //     .y1(d => yDrawdownScale(+d.RelEquity)));


  // Индикаторы на графике цены
  svg.append("path")
    .datum(indicator)
    .attr("class", "indicator line")
    .attr("clip-path", "url(#clip)")
    .attr("d", d3.line().x(d => x(d.date)).y(d => y(d.sig_up)));
  svg.append("path")
    .datum(indicator)
    .attr("class", "indicator line")
    .attr("clip-path", "url(#clip)")
    .attr("d", d3.line().x(d => x(d.date)).y(d => y(d.sig_dn)));

  // svg.append("path")
  //   .datum(indicator)
  //   .attr("class", "indicator_ma line")
  //   .attr("clip-path", "url(#clip)")
  //   .attr("d", d3.line().x(d => x(d.date)).y(d => y(d.ma)));


  // add the Y gridlines
  svg.append("g")
    .attr("class", "grid")
    .call(
      d3.axisLeft(yDrawdownScale).ticks(5).tickSize(-width).tickFormat("")
    )
  // add the Y gridlines
  svg.append("g")
    .attr("class", "grid")
    .call(
      d3.axisLeft(yValueScale).ticks(5).tickSize(-width).tickFormat("")
    )

  svg.selectAll("g.x.axis").call(xAxis);
  svg.selectAll("g.x-axis-2").call(xAxis1);

  svg.selectAll("g.y.axis").call(yAxis);
  svg.selectAll("g.y-axis").call(yValueAxis);
  svg.selectAll("g.y-axis-dd").call(yDrawdownAxis);
}

function enter(d) {
  valueText.style("display", "inline");
  refreshText(d);
}

function out() {
  valueText.style("display", "none");
}

function refreshText(d) {
  valueText.text(
    "Trade: " + dateFormat(d.date) + ", " + d.type + ", " + valueFormat(d.price)
  );
}

run();

