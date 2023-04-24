"use strict";

// @ts-ignore
import * as d3 from "https://cdn.skypack.dev/d3@7";


export class NavChart {

  margin = { top: 30, right: 70, bottom: 30, left: 70 }

  height = 80

  constructor(chartArea, mainChart, performanceChart) {

    this.chartArea = d3.select(chartArea)

    this.mainChart = mainChart
    this.performanceChart = performanceChart

    this.data = mainChart.data

    const m = this.margin

    this.width = chartArea.clientWidth - m.left - m.right

    this.svg = this.chartArea.append("svg")
      .attr("width", "100%")
      .attr("height", this.height + m.top + m.bottom)
      .append("g")
      .attr("transform", `translate(${m.left},${m.top})`);

    this.chart = this.svg
      .append("g")
      .attr("id", "chart_0")

    this.path = this.chart
      .append("g")
      .attr("id", "chart_nav_path")
      .append("path")
      .attr("clip-path", "url(#clip)")
      .attr("fill", "none")
      .attr("stroke", "red")
      .attr("stroke-width", 1)
      .attr("stroke-miterlimit", 1)
      .attr("d", "");

    this.shadeLeft = this.chart
      .append("rect")
      .attr("x", 0)
      .attr("width", 0)
      .attr("height", this.height)
      .attr("fill", "#000")
      .attr("fill-opacity", 0.1)

    this.shadeRight = this.chart
      .append("rect")
      .attr("x", this.width)
      .attr("width", 0)
      .attr("height", this.height)
      .attr("fill", "#000")
      .attr("fill-opacity", 0.1)

    this.overlay = this.chart
      .append("rect")
      .classed("border", true)
      .attr("fill", "#fff")
      .attr("fill-opacity", "0")
      .attr("x", 0)
      .attr("y", 0)
      .attr("width", this.width)
      .attr("height", this.height)

    this.createAxes()

    this.line = d3.line()
      .x(d => this.xScale(d.idx))
      .y(d => this.yScale(d.close))

    this.resample(this.data)

    this.draw(this.data)

    this.mainChart.onAfterZoom = () => {
      // взять диапазон основного графика
      const range = this.mainChart.xScaleZoomed.domain()

      const rangeClient = range.map(this.mainChart.xScale)

      // подвинуть границы brush под границы основного графика
      this.chart.call(this.brush.move, rangeClient)

      this.shadeLeft.attr("width", Math.max(0, rangeClient[0]))
      this.shadeRight.attr("x", Math.max(0, rangeClient[1]))
      this.shadeRight.attr("width", Math.max(0, this.width - rangeClient[1]))

      // let dt0 = this.mainChart.data[Math.round(range[0])].date;
      // let dt1 = this.mainChart.data[Math.round(range[1])].date;

      this.performanceChart.zoomToRange(range)
    }

    const range = this.mainChart.xScaleZoomed.domain()
    this.performanceChart.zoomToRange(range)

    // Копирую подписи горизонтальной оси с основного графика
    this.xAxis = (g, scale) => g
      .attr("transform", `translate(0,${this.height})`)
      .call(
        d3.axisBottom(this.mainChart.xScale)
        .tickSizeOuter(0)
        .tickValues(this.mainChart.timeTickValues)
        .tickFormat((val) => this.mainChart.timeTickFormat(val))
      )
    this.drawAxes();

  }

  resample(data) {
    const small = []
    const step = Math.max(1, Math.round(data.length / 500))
    for (let i = 0; i < data.length; i += step) {
      small.push(data[i])
    }
    this.data = small
  }

  verticalScale(scale, data) {
    // Масштаб по вертикали
    let min = d3.min(data, d => +d.low);
    let max = d3.max(data, d => +d.high);
    let v_pad = (max - min) / 10;
    scale.domain([min - v_pad, max + v_pad])
  }

  createScales(data) {

    const dataRange = d3.extent(data, d => d.idx)

    this.xScale = d3.scaleLinear()
      .domain(dataRange)
      .range([0, this.width])

    this.yScale = d3.scaleLinear()
      .range([this.height, 0])

    // Автоматический вертикальный масштаб
    this.verticalScale(this.yScale, data)

  }

  createAxes() {
    this.xAxis = (g, scale) => g
      .attr("transform", `translate(0,${this.height})`)
      .call(
        d3.axisBottom(scale)
          .ticks(5)
          .tickSizeOuter(0)
      )

    this.yAxis = (g, scale) => g
      .attr("transform", `translate(${this.width},0)`)
      .call(
        d3.axisRight(scale)
          .ticks(0)
          .tickSizeOuter(0)
      );
  }

  drawAxes() {
    // нарисовать оси
    this.chart.append("g")
      .call(this.xAxis, this.xScale);

    // this.chart.append("g")
      // .call(this.yAxis, this.yScale);
  }

  drawLine(data) {
    this.path.attr("d", this.line(data));
  }

  // Обработка события brush
  onBrushed(event) {
    if (event.sourceEvent && event.selection) {
      const s0 = event.selection[0];
      const s1 = event.selection[1];
      const [x0, x1] = [s0, s1].map(this.xScale.invert);
      if (x0 || x1) {
        const scale = this.width / (s1 - s0);
        this.mainChart.zoomTo(scale, -s0);
      }
    }
  }

  setupBrush() {
    // навешивается brush
    this.brush = d3.brushX()
      .extent([[0, 0], [this.width, this.height]])
      .on("brush", (e) => { this.onBrushed(e) })

    // сначала выбрано всё
    const defaultSelection = this.xScale.range();

    this.chart
      .call(this.brush)
      .call(this.brush.move, defaultSelection);
  }

  draw(data) {
    this.createScales(data);
    // this.drawAxes();
    this.setupBrush();
    this.drawLine(data);
  }

}