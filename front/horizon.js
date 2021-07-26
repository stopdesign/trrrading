const parseDate = d3.timeParse('%Y-%m-%d');
const dateFormat = d3.timeFormat('%Y-%m-%d %H:%M');
const valueFormat = d3.format('+.2f');
const valueFormat2 = d3.format('+.2f');

const overlap = 5;

const color = i => d3["schemeRdBu"][overlap * 2 + 1][i + (i >= 0) + overlap]

const margin = ({top: 20, right: 10, bottom: 0, left: 100})

const width = 2000;
const step = 40;

const files = [
  "res/OIH.ARCA_ChannelBreakout_300-stats.csv",
  "res/COPX.ARCA_ChannelBreakout_600-stats.csv",
  "res/ARKK.ARCA_ChannelBreakout_700-stats.csv",
  "res/AMZA.ARCA_ChannelBreakout_500-stats.csv",
  "res/EMQQ.ARCA_ChannelBreakout_400-stats.csv",
  "res/BLOK.ARCA_ChannelBreakout_1000-stats.csv",
  "res/URA.ARCA_ChannelBreakout_500-stats.csv",
  "res/ROBO.ARCA_ChannelBreakout_900-stats.csv",
]

const height = (files.length) * (step + 8) + margin.top + margin.bottom


async function run() {

  let series = [];
  let dates;

  for (const file of files) {
    console.log(file);
    let stats = await d3.csv(file);
    dates = stats.map(d => parseDate(d.Date));
    let values = stats.map(d => +d.Change);
    series.push({
      name: file, //  .substring(4, 13).replace(/[^A-Z.]+$/g, ''),
      values: values,
    });
  }
  let min_len = d3.min(series, d => d.values.length);

  series.map(ser => {
    ser.values = ser.values.slice(0, min_len);
  });

  let data = {
    dates: dates,
    series: series,
  }

  // console.log(data);

  const area = d3.area()
    .curve(d3.curveBasis)
    .defined(d => {
      // console.log(d);
      return !isNaN(d)
    })
    // .defined(d => !isNaN(d))
    .x((d, i) => x(data.dates[i]))
    .y0(0)
    .y1(d => {
      // console.log('>>>', d, y(d));
      return y(d)
    })

  const max = d3.max(data.series, d => d3.max(d.values)) / 1.5;
  const y = d3.scaleLinear()
    .domain([-max, max])
    .range([overlap * step, -overlap * step]);

  const x = d3.scaleUtc()
    .domain(d3.extent(data.dates))
    .range([0, width])

  const xAxis = g => g
    .attr("transform", `translate(0,${margin.top})`)
    .call(
      d3.axisTop(x)
        .ticks(width / 500)
        .tickSizeOuter(0)
        .tickSizeInner(-height)
    )
    // .call(g => g.select(".domain").remove())
  // var xAxis = d3.svg.axis()
  //   .scale(x)
  //   .orient("bottom")
  //   .tickSize(6, 0)
  //   .tickFormat(d3.time.format("%m/%d"));

  const svg = d3.select("body").append("svg")
    .attr("class", "horizon")
    .style("font", "14px sans-serif")
    .style("font-weight", "500")
    .style("letter-spacing", "0.5px")
    .style("text-shadow", "-1px -1px 0 #eee, 1px -1px 0 #eee, -1px 1px 0 #eee, 1px 1px 0 #eee")
    .attr("width", width)
    .attr("height", height)
    .attr("viewBox", [0, 0, width, height])
    .append("g")
    .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

  const g = svg.append("g")
    .selectAll("g")
    .data(data.series.map(d => Object.assign({
      clipId: "clip_id_" + d.name,
      pathId: "path_id_" + d.name,
    }, d)))
    .join("g")
      .attr("transform", (d, i) => `translate(0,${i * (step + 7) + margin.top})`);

  g.append("clipPath")
      .attr("id", d => d.clipId)
    .append("rect")
      .attr("width", width)
      .attr("height", step);

  g.append("defs").append("path")
      .attr("id", d => d.pathId)
      .attr("d", d => {
        return area(d.values)
      });

  g.append("g")
      .attr("clip-path", d => "url(#" + d.clipId + ")")
    .selectAll("use")
    .data(d => Array.from(
      {length: overlap * 2},
      (_, i) => Object.assign({index: i < overlap ? -i - 1 : i - overlap}, d)
    ))
    .enter().append("use")
      .attr("fill", d => color(d.index))
      .attr("transform", d => 1 && d.index < 0
          ? `scale(1,-1) translate(0,${d.index * step})`
          : `translate(0,${(d.index + 1) * step})`)
      .attr("xlink:href", d => "#" + d.pathId);

  g.append("text")
      .attr("x", -70)
      .attr("y", step / 2)
      .attr("dy", "0.35em")
      .text(d => {
        return d.name.substring(4, 8).replace(/\./, '') + "-" + d.name.replace(/[^0-9]+/g, '')
      });

  svg.append("g")
      .attr("class", "x-axis")
      .call(xAxis);


}

run();
