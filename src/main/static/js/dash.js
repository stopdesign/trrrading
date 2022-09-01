
// set the dimensions and margins of the graph
const margin = {top: 10, right: 0, bottom: 40, left: 0},
    width = 2400 - margin.left - margin.right,
    height = 130 - margin.top - margin.bottom;


function pad(num) {
  return ("0" + num).slice(-2)
}


function draw_chart(el, data, symbol) {
  const svg = d3.select(el)
    .append("svg")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom)
    .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

  // List of subgroups = header of the csv files = soil condition here
  const subgroups = data.columns.slice(1)

  const subdata = data.filter(d => d['ticker'] === symbol)

  // List of groups = species here = value of the first
  // column called group -> I show them on the X axis
  const groups = subdata.map(d => (d.hour))



  // Add X axis
  const x = d3.scaleBand()
      .domain(groups)
      .range([0, width])
      .padding([0.2])

  const x_axis = d3.axisBottom(x)
    .tickPadding(4)
    .tickSizeOuter(0)
    .tickSizeInner(5)
    // .tickFormat(a => pad(new Date(a).getHours()));
    .tickFormat(a => pad(new Date(a + " UTC").getHours()));

  const x_axis_day = d3.axisBottom(x)
    .tickPadding(23)
    .tickSizeInner(0)
    .tickFormat(a => {
      let dt = new Date(a + " UTC");
      if (!dt.getHours()) {
        return dt.toLocaleDateString("en-GB", {day: "2-digit", month: "short"});
      }
    });

  // Add Y axis
  const y = d3.scaleLinear()
    .domain([0, 60])
    .range([height, 0]);
  // svg.append("g")
  //   .call(d3.axisLeft(y).ticks(5));

  // color palette = one color per subgroup
  const color = d3.scaleOrdinal()
    .domain(subgroups)
    .range([
      '#ffffff',  // hour
      '#40aabd',  // ok
      '#000000',  // error
      '#d5d5d5',  // closed - светло-серый
      '#777777',  // empty  - темно-серый
      '#ddeeee',  // delay  - голубой
      '#ff8e3f',  // fix    - оранжевый
      '#da5ee0',  // late   - magenta
      '#f5f5f5',  // no_data
      '#00ff00',
      '#0000ff',
      '#ff00ff',
    ])

  //stack the data? --> stack per subgroup
  const stackedData = d3.stack()
    .keys(subgroups)
    (subdata)

  // Show the bars
  svg.append("g")
    .selectAll("g")
    // Enter in the stack data = loop key per key = group per group
    .data(stackedData)
    .join("g")
      .attr("fill", d => color(d.key))
      .selectAll("rect")
      // enter a second time = loop subgroup per subgroup to add all rectangles
      .data(d => d)
      .join("rect")
        .attr("x", d => x(d.data.hour))
        .attr("y", d => y(d[1]))
        .attr("height", d => y(d[0] || 0) - y(d[1] || 0))
        .attr("width", x.bandwidth())


  svg.append("g")
    .attr("transform", `translate(0, ${height})`)
    .call(x_axis)
    .selectAll("text")
    .attr('font-size', "10px")
    .style('fill',  function(d) {
      // var dt1 = new Date(d + " UTC");
      // var dt2 = new Date(d + " UTC");
      // dt1.setMonth(0, 0);
      // t = Math.round((dt1 - dt2) / 8.64e7);
      // if (t % 2) {
      //   return "#aa5577"
      // } else {
      //   return "#338899"
      // }
      let hh = new Date(d + " UTC").getHours() * 9 + 10;
      return "rgb(" + hh + "," + hh + ","+ hh +")";
    });

  svg.append("g")
    .attr("transform", `translate(10, ${height})`)
    .call(x_axis_day)
    .selectAll("text")
    .attr('font-size', "10px")
    .style('fill',  function(d) {
      var wd = (new Date(d + " UTC")).getDay();
      if (wd === 0 || wd === 6) {
        return "#cc5533"
      } else {
        return "#339977"
      }
      // let hh = new Date(d + " UTC").getHours() * 9 + 10;
      // return "rgb(" + hh + "," + hh + ","+ hh +")";
    });
}


// Parse the Data
d3.csv("./dash.csv").then( function(data) {

  const symbols = []
  for (const line of data) {
    if (symbols.indexOf(line.ticker) < 0) {
      symbols.push(line.ticker)
    }
  }

  for (const symbol of symbols.sort()) {
    const element = document.createElement('h2')
    element.textContent = symbol
    document.body.append(element)

    const svg_container = document.createElement('div')
    document.body.append(svg_container)
    draw_chart(svg_container, data, symbol)
  }

})
