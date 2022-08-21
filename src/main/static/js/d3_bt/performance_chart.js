"use strict"

// @ts-ignore
import * as d3 from "https://cdn.skypack.dev/d3@7"


function randId() {
  return Math.random().toString(36).substring(2, 10)
}


export class PerformanceChart {

  margin = { top: 40, right: 70, bottom: 50, left: 70 }

  height = 150
  width = 1800

  chartPadding = 0.05

  constructor(chartArea, data) {

    this.bisectDate = d3.bisector(function (d) { return d.date }).left

    this.chartArea = d3.select(chartArea)
    this.data = data

    const m = this.margin

    this.svg = this.chartArea.append("svg")
      .attr("width", "100%")
      .attr("height", this.height + m.top + m.bottom)
      .append("g")
      .attr("transform", `translate(${m.left},${m.top})`)

    this.chart = this.svg
      .append("g")
      .attr("id", "chart_0")

    const clipId = "clip_" + randId()

    this.chart
      .append("clipPath")
      .attr("id", clipId)
      .append("rect")
      .attr("x", 0)
      .attr("y", 0)
      .attr("width", this.width)
      .attr("height", this.height)

    this.pathDeposit = this.chart
      .append("path")
      .classed("count", true)
      .attr("clip-path", `url(#${clipId})`)
      .attr("fill", "#94ddef")
      // .attr("stroke", "#62BEFF")
      .attr("d", "")

    this.pathDrawdown = this.chart
      .append("path")
      .classed("count", true)
      .attr("clip-path", `url(#${clipId})`)
      .attr("fill", "#ffb5a5")
      .attr("fill-opacity", 0.6)
      // .attr("stroke", "#E37860")
      .attr("d", "")

    this.overlay = this.chart
      .append("rect")
      .classed("border", true)
      .attr("fill", "#fff")
      .attr("fill-opacity", "0")
      .attr("x", 0)
      .attr("y", 0)
      .attr("width", this.width)
      .attr("height", this.height)

    this.gx = this.chart
      .append("g")
      .attr("transform", `translate(0,${this.height})`)

    this.gxGrid = this.chart
      .append("g")
      .classed("grid", true)
      .attr("transform", `translate(0,${this.height})`)

    this.gy = this.chart
      .append("g")
      .attr("transform", `translate(${this.width},0)`)

    this.depositArea = d3.area()
      .curve(d3.curveStepAfter)
      .x(d => this.xScaleZoomed(d.idx))
      .y0(this.height)
      .y1(d => this.yScale(d.net_value))

    this.drawdownArea = d3.area()
      .curve(d3.curveStepAfter)
      .x(d => this.xScaleZoomed(d.idx))
      .y0(0)
      .y1(d => this.yDrawdownScale(d.drawdown))

    this.resample()

    this.data = this.calcDrawdown(this.data)

    this.draw(this.data)
  }

  resample() {

    var data = this.data

    var bisect = d3.bisector(function (d) { return d.time }).left

    // const getInterval = dt => dt.getDay()
    const getInterval = dt => dt.getHours()

    const small = [data[0]]
    let prevBar = data[0]
    for (const bar of data) {
      if (getInterval(prevBar.date) != getInterval(bar.date)) {
        small.push({
          date: bar.date,
          time: bar.time,
          drawdown: bar.drawdown,
          idx: data[bisect(data, bar.time, 1)].idx,
          net_value: bar.net_value,
        })
      }
      prevBar = bar
    }
    small.push(data.at(-1))

    this.data = small

  }

  draw(data) {
    this.createScales(data)
    this.createAxes()
    this.drawAxes(data)
    this.drawLine(data)
  }

  verticalScale(data) {
    // Масштаб по вертикали
    let min = +1000000
    let max = -1000000
    for (const d of data) {
      if (d.net_value < min) min = d.net_value
      if (d.net_value > max) max = d.net_value
    }
    this.yScale.domain([min, max])
    this.yDrawdownScale.domain([0, max - min])
  }

  createScales(data) {

    const dataRange = d3.extent(data, d => d.idx)

    this.xScale = d3.scaleLinear()
      .domain(dataRange)
      .range([0, this.width])

    this.xScaleZoomed = this.xScale.copy()

    this.yScale = d3.scaleLinear()
      .range([this.height, 0])

    this.yDrawdownScale = d3.scaleLinear()
      .range([0, this.height])

    this.verticalScale(data)
  }

  createAxes() {
    this.xAxis = d3.axisBottom(this.xScaleZoomed)
      .ticks(5)
      .tickSizeOuter(0)

    this.xAxisGrid = d3.axisBottom(this.xScaleZoomed)
      .ticks(5)
      .tickSize(-this.height)
      .tickSizeOuter(0)
      .tickFormat("")

    this.yAxis = d3.axisRight(this.yScale)
      .ticks(4)
      .tickSizeOuter(0)
      .tickFormat(d => d.toFixed(0))
  }

  drawAxes(data) {
    // Автоматический вертикальный масштаб
    this.verticalScale(data)

    // нарисовать оси
    this.xAxis(this.gx)
    this.yAxis(this.gy)

    this.xAxisGrid(this.gxGrid)
  }

  drawLine(data) {
    const d1 = this.depositArea(data)
    const d2 = this.drawdownArea(data)
    this.pathDrawdown.attr("d", d2)
    this.pathDeposit.attr("d", d1)
  }

  calcDrawdown(data) {
    let max_value = 0
    return data.map((d, idx) => {
      const value = +d.net_value
      max_value = Math.max(max_value, value)
      const drawdown = max_value - value
      return {
        date: d.date,
        time: d.time,
        idx: d.idx,
        net_value: value,
        drawdown: drawdown,
      }
    })
  }

  zoomToRange(range, dates) {

    // TODO: Сейчас range задается датами, 
    // но при одинаковых системах отсчета в data и stats
    // можно будет сделать отсечку по индексу

    // Часть данных, входящая в отображаемый диапазон
    const i0 = Math.max(0, this.bisectDate(this.data, dates[0]) - 2)
    const i1 = this.bisectDate(this.data, dates[1]) + 1

    let dataZoomed = this.data.slice(i0, i1)

    dataZoomed = this.calcDrawdown(dataZoomed)

    // const dataRange = d3.extent(dataZoomed, d => d.idx)

    // console.log(dataRange)

    this.xScaleZoomed.domain(range)

    this.drawLine(dataZoomed)

    this.drawAxes(dataZoomed)

  }


}