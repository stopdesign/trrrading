"use strict"

// @ts-ignore
import * as d3 from "https://cdn.skypack.dev/d3@7"


const getWeekNumber = function (dt) {
  var d = new Date(Date.UTC(dt.getFullYear(), dt.getMonth(), dt.getDate()))
  var dayNum = d.getUTCDay() || 7
  d.setUTCDate(d.getUTCDate() + 4 - dayNum)
  var yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  // @ts-ignore
  return Math.ceil((((d - yearStart) / 86400000) + 1) / 7)
}


export class PriceAroundTrades {

  margin = { top: 40, right: 70, bottom: 50, left: 70 }

  height = 500
  width = 1000

  len = 60 * 5

  chartPadding = 0.05

  constructor(chartArea, data, trades) {

    this.chartArea = d3.select(chartArea)
    this.data = data
    this.trades = trades

    // console.log(data)
    // console.log(trades)

    const m = this.margin

    this.svg = this.chartArea.append("svg")
      .attr("width", "100%")
      .attr("height", this.height + m.top + m.bottom)
      .append("g")
      .attr("transform", `translate(${m.left},${m.top})`)

    this.chart = this.svg
      .append("g")
      .attr("id", "chart_0")

    const pointermoved = (event) => {
      const [xm, ym] = d3.pointer(event)
      console.log(xm, ym, Math.round(ym/2))

      for (const i in this.paths) {
        if (Math.round(ym/2) === parseInt(i)) {
          this.paths[i].attr("stroke", "#05d")  // style
          this.paths[i].attr("stroke-opacity", 1)
          this.paths[i].attr("stroke-width", 1)
        } else {
          this.paths[i].attr("stroke", "#666")
          this.paths[i].attr("stroke-opacity", 0.2)
          this.paths[i].attr("stroke-width", 1)
        }
      }

    }

    this.overlay = this.chart
      .append("rect")
      .classed("border", true)
      .attr("fill", "#fff")
      .attr("fill-opacity", "0")
      .attr("x", 0)
      .attr("y", 0)
      .attr("width", this.width)
      .attr("height", this.height)
      .on("pointermove", pointermoved)

    this.gx = this.chart
      .append("g")
      .attr("transform", `translate(0,${this.height})`)

    this.gy = this.chart
      .append("g")
      .attr("transform", `translate(${this.width},0)`)

    this.draw(this.data)
  }

  draw(data) {
    this.createScales(data)
    this.drawLine(data)
  }

  createScales(data) {
    this.xScale = d3.scaleLinear()
      .domain([-this.len, this.len])
      .range([0, this.width])
    
    const price_diffs = []
    for (const trade of this.trades) {
      if (trade.side == "buy") {
        
        let max_idx = this.data.length - 1
        if (trade.id < this.trades.length - 1) {
          max_idx = this.trades[trade.id + 1].idx
        }

        const i0 = Math.max(trade.idx - this.len, 0)
        const i1 = Math.min(trade.idx + this.len + 1, max_idx)

        const trade_data = this.data.slice(i0, i1)
        price_diffs.push(...trade_data.map(d => d.close - trade.price))
      }
    }

    const range = d3.extent(price_diffs)
    const max_from_zero = Math.max(-range[0], range[1])

    this.yScale = d3.scaleLinear()
      .domain([-max_from_zero, max_from_zero])
      .range([this.height, 0])
  }

  drawLine(data) {

    this.paths = []
    const lines = this.chart.append("g")
    
    this.chart.append("g")
      .append("circle")
      .attr("r", 5)
      .attr("cx", this.width / 2)
      .attr("cy", this.height / 2)
      .attr("fill", "#d00")


    let prevBar = this.data[0]
    let fake_trades = []
    for (const d of this.data) {
      if (d.date.getDay() != prevBar.date.getDay()) {
        fake_trades.push({
          "id": fake_trades.length,
          "idx": d.idx,
          "price": d.open,
          "side": "buy",
        })
      }
      prevBar = d
    }

    // const trades = this.trades
    const trades = fake_trades

    for (const trade of trades) {
      if (trade.side == "buy") {

        let max_idx = this.data.length - 1
        if (trade.id < trades.length - 1) {
          max_idx = trades[trade.id + 1].idx
        }

        const i0 = Math.max(trade.idx - this.len, 0)
        const i1 = Math.min(trade.idx + this.len + 1, max_idx)
        
        const trade_data = this.data.slice(i0, i1)

        const line = d3.line()
          .x(d => this.xScale(d.idx - trade.idx))
          .y(d => this.yScale(d.close  - trade.price))

        this.paths.push(
          lines.append("path")
            .classed("count", true)
            .attr("fill", "none")
            .attr("stroke", "#666")
            .attr("stroke-opacity", "0.5")
            .attr("stroke-width", 1)
            .attr("d", line(trade_data))
        )
      }
    }

  }

}