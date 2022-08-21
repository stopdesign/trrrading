"use strict"

// @ts-ignore
import * as d3 from "https://cdn.skypack.dev/d3@7"


const getWeekNumber = function (dt) {
  var d = new Date(Date.UTC(dt.getFullYear(), dt.getMonth(), dt.getDate()));
  var dayNum = d.getUTCDay() || 7
  d.setUTCDate(d.getUTCDate() + 4 - dayNum)
  var yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  // @ts-ignore
  return Math.ceil((((d - yearStart) / 86400000) + 1) / 7)
}


export class WeekleyChart {

  margin = { top: 40, right: 80, bottom: 180, left: 40 }

  height = 150
  width = 1200

  chartPadding = 0.05

  constructor(chartArea, data) {

    this.chartArea = d3.select(chartArea)
    this.data = data

    console.log(data)

    this.wData = []
    let prevBar = structuredClone(data[0])
    for (const bar of data) {
      const curWeek = getWeekNumber(prevBar.date)
      const newWeek = getWeekNumber(bar.date)
      if (prevBar.date > bar.date) {
        console.log(prevBar.date, prevBar.time, bar.date, bar.time)
      }
      if (curWeek != newWeek) {
        let pnl = 0
        if (this.wData.length) {
          pnl = bar.net_value - this.wData[this.wData.length - 1]["net_value"]
        }
        this.wData.push({
          week: curWeek,
          date: new Date(prevBar.date),
          pnl: Math.round(pnl),
          net_value: bar.net_value,
        })
      }
      prevBar = structuredClone(bar)
    }
    // console.log(this.wData)

    const m = this.margin

    this.svg = this.chartArea.append("svg")
      .attr("width", "100%")
      .attr("height", "250")
      .append("g")
      .attr("transform", `translate(${m.left},${m.top})`)

    this.chart = this.svg
      .append("g")
      .attr("id", "chart_0")

    this.gx = this.chart
      .append("g")
      .attr("transform", `translate(0,${this.height})`)

    this.gy = this.chart
      .append("g")
      .attr("transform", `translate(${this.width},0)`)

    this.draw(this.wData)
  }

  draw(data) {
    this.createScales(data)
    this.createAxes()
    this.drawAxes(data)
    this.drawLine(data)
  }

  verticalScale(data) {
    // Масштаб по вертикали
    const min = d3.min(data, d => +d.pnl)
    const max = d3.max(data, d => +d.pnl)
    this.yScale.domain([min, max])
  }

  createScales(data) {

    this.xScale = d3.scaleBand()
      .domain(data.map(d => d.date))
      .range([0, this.width])
      .padding(0.1)

    this.yScale = d3.scaleLinear()
      .range([this.height, 0])

    this.verticalScale(data)
  }

  createAxes() {
    this.xAxis = d3.axisBottom(this.xScale)
      .tickSizeOuter(0)
      .tickFormat(d3.timeFormat("%Y-%m-%d"))

    this.yAxis = d3.axisRight(this.yScale)
      .ticks(5)
      .tickFormat(d => d.toFixed(2))
  }

  drawAxes(data) {
    // Автоматический вертикальный масштаб
    this.verticalScale(data)

    // нарисовать оси
    this.xAxis(this.gx)
    this.yAxis(this.gy)
  }

  drawLine(data) {
    console.log(data);
    this.chart.append("g")
      .attr("class", "bars")
      .selectAll("rect")
      .data(data)
      .join("rect")
      .attr("fill", d => d.pnl > 0 ? "#080" : "#d00")
      .attr("x", d => this.xScale(d.date))
      .attr("y", d => d.pnl < 0 ? this.yScale(0) : this.yScale(d.pnl))
      .attr("height", d => Math.abs(this.yScale(0) - this.yScale(d.pnl)))
      .attr("width", this.xScale.bandwidth())
  }

  //   zoomToRange(range) {

  //     // Часть данных, входящая в отображаемый диапазон
  //     const dataZoomed = this.data.filter(function (d) {
  //       return (range[0] <= d.date) && (d.date <= range[1])
  //     })

  //     const dataRange = d3.extent(dataZoomed, d => d.idx)

  //     this.xScaleZoomed.domain(dataRange)

  //     this.drawLine(dataZoomed)

  //     this.drawAxes(dataZoomed)

  //   }


}