"use strict"

// @ts-ignore
import * as d3 from "https://cdn.skypack.dev/d3@7"

import { resampleOhlcv } from "./ohlc.js"


function randId() {
  return Math.random().toString(36).substring(2, 10)
}


const getWeekNumber = function (dt) {
  var d = new Date(Date.UTC(dt.getFullYear(), dt.getMonth(), dt.getDate()))
  var dayNum = d.getUTCDay() || 7
  d.setUTCDate(d.getUTCDate() + 4 - dayNum)
  var yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  // @ts-ignore
  return Math.ceil((((d - yearStart) / 86400000) + 1) / 7)
}



let last_info_update = new Date().getTime()
function print_info(data, data_z) {

  const $d3ChartInfo = document.querySelector('#d3_charts_info')

  // Redraw throttle
  const now = new Date().getTime()
  if (now - last_info_update < 66) return
  last_info_update = now

  // Вывести количество SVG-элементов на странице
  const svgElems = ["clipPath", "circle", "rect", "path", "text", "g", "line"]
    .map(tag => document.getElementsByTagName(tag).length)
    .reduce((res, length) => res + length)

  // Количество движений внутри всех path
  let pathTurns = 0
  for (const path of document.querySelectorAll('svg path.count')) {
    const d = path.getAttribute("d")
    if (d) pathTurns += (d.match(/[MLVH]/g) || []).length
  }

  $d3ChartInfo.innerHTML = `<p>Source bars: ${data.length}</p>
    <p>Scaled bars: ${data_z.length}</p>
    <p>SVG elements: ${svgElems}</p>
    <p>Path turns: ${pathTurns}</p>`
}



export class PriceChart {

  margin = { top: 40, right: 70, bottom: 50, left: 70 }

  height = 500

  chartPadding = 0.15

  constructor(chartArea, data, trades, indicators) {

    this.cursorPos = null
    this.cursorPosY = null

    this.bisectDate = d3.bisector(function (d) { return d.date }).left
    this.bisectTime = d3.bisector(function (d) { return d.time }).left
    this.bisectIdx = d3.bisector(function (d) { return d.idx }).left

    this.chartArea = d3.select(chartArea)
    this.data = data
    this.trades = trades

    this.indicators = indicators

    this.dateByIdx = []

    this.xAxisFormat = d3.timeFormat("%Y-%m-%d")
    this.xCrosshairLabelFormat = d3.timeFormat("%Y-%m-%d  %H:%M")

    // Для каждой сделки определить положение в координатах шкалы цен (idx)
    for (const trade of this.trades) {
      let bar = data[this.bisectDate(data, trade.date)]
      if (bar) trade.idx = bar.idx
    }

    this.createAxes()

    const m = this.margin

    this.width = chartArea.clientWidth - m.left - m.right

    this.svg = this.chartArea.append("svg")
      .attr("width", "100%")
      .attr("height", this.height + m.top + m.bottom)
      .append("g")
      .attr("transform", `translate(${m.left},${m.top})`)

    this.drawGrid()

    this.chart = this.svg
      .append("g")
      .attr("id", "price_chart")

    this.clipId = "clip_" + randId()

    this.chart
      .append("clipPath")
      .attr("id", this.clipId)
      .append("rect")
      .attr("x", 0)
      .attr("y", 0)
      .attr("width", this.width)
      .attr("height", this.height)

    this.path = this.chart
      .append("g")
      .append("path")
      .classed("count", true)
      .attr("clip-path", `url(#${this.clipId})`)
      .attr("fill", "none")
      .attr("stroke", "steelblue")
      .attr("stroke-width", 1)
      .attr("d", "")

    for (const indicator of this.indicators) {
      for (const key in indicator.chart) {
        const params = indicator.chart[key]
        // console.log(params)
        const color = params.color || "black"
        if (params.type == "line") {
          indicator.chart[key]["shape"] = this.chart
            .append("g")
            .append("path")
            .classed("count", true)
            .attr("clip-path", `url(#${this.clipId})`)
            .attr("fill", "none")
            .attr("stroke", color)
            .attr("stroke-width", 1)
            .attr("d", "")
        }
      }
    }

    this.tradesLayer = this.chart
      .append("g")
      .attr("id", "trades")
      .attr("clip-path", `url(#${this.clipId})`)

    this.line = d3.line()
      .x(d => this.xScaleZoomed(d.idx))
      .y(d => this.yScale(d.close))

    this.resample(data)

    this.draw(this.data)

  }

  createCrosshairStuff() {

    this.crosshair = this.chart
      .append("line")
      .attr("clip-path", `url(#${this.clipId})`)
      .attr("fill", "none")
      .attr("stroke", "#999999")
      .attr("stroke-width", "0.5px")
      .attr("stroke-dasharray", "5 5")
      .attr("y1", 0)
      .attr("y2", this.height)
      .attr("d", "")

    this.crosshairY = this.chart
      .append("line")
      .attr("clip-path", `url(#${this.clipId})`)
      .attr("fill", "none")
      .attr("stroke", "#999999")
      .attr("stroke-width", "0.5px")
      .attr("stroke-dasharray", "5 5")
      .attr("x1", 0)
      .attr("x2", this.width)
      .attr("d", "")

    // Расширяет this.chart до нужных размеров,
    // чтобы можно было навесить события мыши для зума.
    // И для правильной работы событий crosshair.
    this.overlay = this.chart
      .append("rect")
      .classed("border", true)
      .attr("fill", "#fff")
      .attr("fill-opacity", "0")
      .attr("x", 0)
      .attr("y", 0)
      .attr("width", this.width)
      .attr("height", this.height)

    this.crosshairLabelTimeBox = this.svg
      .append("g")
      .attr("id", "crosshair_label_time")

    this.crosshairLabelTimeBox.append("rect")
      .attr("x", -63)
      .attr("y", 0)
      .attr("width", 126)
      .attr("height", 26)

    this.crosshairLabelTimeVal = this.crosshairLabelTimeBox.append("text")
      .attr("dy", 18)
      .attr("dx", 0)
      .attr("text-anchor", "middle")


    // левый блок цены crosshair

    this.crosshairLabelPriceBoxL = this.svg
      .append("g")
      .attr("id", "crosshair_label_price_l")

    this.crosshairLabelPriceBoxL.append("rect")
      .attr("x", -50)
      .attr("y", -13)
      .attr("width", 50)
      .attr("height", 26)

    this.crosshairLabelPriceValL = this.crosshairLabelPriceBoxL.append("text")
      .attr("dy", 5)
      .attr("dx", -43)
      .attr("text-anchor", "right")

  }

  updateCrosshairLabel = (x, txt) => {
    this.crosshairLabelTimeBox.attr("transform", `translate(${x},${this.height})`)
    this.crosshairLabelTimeVal.text(txt)
  }

  updateCrosshairLabelY = (y, txt) => {
    this.crosshairLabelPriceBoxL.attr("transform", `translate(0,${y})`)
    this.crosshairLabelPriceValL.text(txt)
  }

  resample(data) {
    let prevBar

    // time ticks
    this.dateByIdx = []
    for (let bar of data) {
      this.dateByIdx.push(bar.date)
    }
    // console.log(this.dateByIdx)

    this.data_10m = resampleOhlcv(data, { baseTimeframe: 60, newTimeframe: 600 })
    this.data_10m = this.data_10m.map((d, idx) => ({
      date: new Date(d.time),
      time: d.time,
      open: +d.open,
      high: +d.high,
      low: +d.low,
      close: +d.close,
      ind: data[this.bisectTime(data, d.time)].ind,
      idx: data[this.bisectTime(data, d.time)].idx,
    }))

    this.data_1h = resampleOhlcv(data, { baseTimeframe: 60, newTimeframe: 3600 })
    this.data_1h = this.data_1h.map((d, idx) => ({
      date: new Date(d.time),
      time: d.time,
      open: +d.open,
      high: +d.high,
      low: +d.low,
      close: +d.close,
      ind: data[this.bisectTime(data, d.time)].ind,
      idx: data[this.bisectTime(data, d.time)].idx,
    }))


    // Первый интервал каждого дня
    this.data_1d = []
    prevBar = this.data_1h[0]
    for (const d of this.data_1h) {
      if (d.date.getDay() != prevBar.date.getDay()) {
        this.data_1d.push({
          date: new Date(d.time),
          time: d.time,

          // Это не настоящий OHLC, но для такого масштаба сойдет
          open: +d.open,
          high: +d.high,
          low: +d.low,
          close: +d.close,

          idx: data[this.bisectTime(data, d.time, 1)].idx,
        })
      }
      prevBar = d
    }

    // Первый интервал каждой недели
    this.data_1w = []
    prevBar = this.data_1h[0]
    for (const d of this.data_1h) {
      if (getWeekNumber(d.date) != getWeekNumber(prevBar.date)) {
        this.data_1w.push({
          date: new Date(d.time),
          time: d.time,
          idx: data[this.bisectTime(data, d.time, 1)].idx,
        })
      }
      prevBar = d
    }

    // Первый день каждого месяца
    this.data_1m = []
    prevBar = this.data_1d[0]
    for (const d of this.data_1d) {
      if (d.date.getMonth() != prevBar.date.getMonth()) {
        this.data_1m.push({
          date: new Date(d.time),
          time: d.time,
          idx: data[this.bisectTime(data, d.time, 1)].idx,
        })
      }
      prevBar = d
    }

  }

  // Линия цены или OHLC при разных уровнях зума
  draw_price_line_for_data(data_z) {

    let path_svg = ""
    let stroke = "#999"
    let strokeWidth = 1

    const x = this.xScaleZoomed
    const y = this.yScale

    const range = x.domain()

    const line_zoomed = d3.line()
      .x(d => x(d.idx))
      .y(d => y(d.close))

    let small = []

    const dataSize = data_z.length

    let draw_indicators = false

    if (dataSize > 100000) {
      // часовые данные, линия
      const i0 = this.bisectIdx(this.data_1d, range[0])
      const i1 = this.bisectIdx(this.data_1d, range[1])
      small = this.data_1d.slice(i0, i1)
      path_svg = line_zoomed(small)
      // stroke = "#05c"  // синий
    }
    else if (dataSize > 30000) {
      // часовые данные, линия
      const i0 = this.bisectIdx(this.data_1h, range[0])
      const i1 = this.bisectIdx(this.data_1h, range[1])
      small = this.data_1h.slice(i0, i1)
      path_svg = line_zoomed(small)
      // stroke = "#05c"  // синий
    }
    else if (dataSize > 10000) {
      // 10-минутные данные, линия
      const i0 = this.bisectIdx(this.data_10m, range[0])
      const i1 = this.bisectIdx(this.data_10m, range[1])
      small = this.data_10m.slice(i0, i1)
      path_svg = line_zoomed(small)
      // stroke = "#a08"  // фиолетовый

      // рисовать индикаторы
      draw_indicators = true
    }
    else if (dataSize > 5000) {
      // 10-минутные данные, вертикальные палки
      const i0 = this.bisectIdx(this.data_10m, range[0])
      const i1 = this.bisectIdx(this.data_10m, range[1])
      small = this.data_10m.slice(i0, i1)
      for (const d of small) {
        const dt = x(d.idx)
        const h = Math.round(y(d.high)) + 0.7
        const l = Math.round(y(d.low)) - 0.7
        path_svg += `M${dt},${l}V${h}`  // зеленый
      }
      // stroke = "#5a5"

      // рисовать индикаторы
      draw_indicators = true
    }
    else if (dataSize > 1500) {
      // минутные данные, вертикальные палки
      small = data_z
      for (const d of small) {
        const dt = Math.round(x(d.idx) * 10) / 10
        const h = Math.round(y(d.high)) + 0.7
        const l = Math.round(y(d.low)) - 0.7
        path_svg += `M${dt},${l}V${h}`
      }
      // stroke = "#f50"    // оранжевый

      // рисовать индикаторы
      draw_indicators = true
    }
    else {
      // минутные данные, OHLC
      small = data_z
      for (const d of small) {
        const dt = Math.round(x(d.idx) * 10) / 10
        const o = Math.round(y(d.open))
        const h = Math.round(y(d.high)) + 0.7
        const l = Math.round(y(d.low)) - 0.7
        const c = Math.round(y(d.close))
        let w = Math.round(600 / dataSize)  // засечки на OHLC
        path_svg += `M${dt},${l}V${h}M${dt},${o}h-${w}M${dt},${c}h${w}`
      }
      // stroke = "#000"

      // рисовать индикаторы
      draw_indicators = true
    }

    if (dataSize > 600) {
      strokeWidth = 1
    } else if (dataSize > 500) {
      strokeWidth = 1.1
    } else if (dataSize > 400) {
      strokeWidth = 1.3
    } else if (dataSize > 300) {
      strokeWidth = 1.5
    } else {
      strokeWidth = 1.7
    }

    if (draw_indicators) {
      this.draw_indicator_lines(small)
    } else {
      this.draw_indicator_lines(false)
    }

    this.path
      .attr("stroke-width", strokeWidth)
      .attr("stroke", stroke)
      .attr("d", path_svg)

    // Вертикальный автомасштаб по сжатым данным
    this.verticalScale(this.yScale, small)

    print_info(data_z, small)
  }

  draw_indicator_lines(data) {
    // индикаторы из meta-конфига + данные из ohlc-файла = нарисовать
    for (const i in this.indicators) {
      const indicator = this.indicators[i]
      for (const key in indicator.chart) {
        const params = indicator.chart[key]
        if (params.type == "line") {
          if (data === false) {
            indicator.chart[key]["shape"].attr("d", "")
          } else {
            const line = d3.line()
              .x(d => this.xScaleZoomed(d.idx))
              .y(d => this.yScale(d.ind[i][key]))
            indicator.chart[key]["shape"].attr("d", line(data))
          }
        }
      }
    }
  }

  createScales(data) {

    const dataRange = d3.extent(data, d => d.idx)

    this.xScale = d3.scaleLinear()
      .domain(dataRange)
      .range([0, this.width])

    this.xScaleZoomed = this.xScale.copy()

    this.yScale = d3.scaleLinear()
      .range([this.height, 0])

    // Автоматический вертикальный масштаб
    this.verticalScale(this.yScale, data)

  }

  draw(data) {
    this.createScales(data)
    this.drawAxes()
    this.createCrosshairStuff()
    this.setupZoom()
    this.drawLine(data)
    this.draw_trades(data, this.trades)
  }

  verticalScale(scale, data) {
    // Масштаб по вертикали
    let min = +1000000
    let max = -1000000
    for (const d of data) {
      if (d.low < min) min = d.low
      if (d.high > max) max = d.high
    }
    const pad = (max - min) * this.chartPadding
    scale.domain([min - pad, max + pad])
  }

  getBestValidIndex(x) {
    return Math.min(Math.max(0, Math.round(x)), this.data.length)
  }

  // Возвращает разные наборы меток оси времени в зависимости от диапазона
  get timeTickValues() {
    let [i0, i1] = this.xScaleZoomed.domain()
    i0 = this.getBestValidIndex(i0)
    i1 = this.getBestValidIndex(i1)
    const [t0, t1] = [this.data[i0].date, this.data[i1].date]

    // диапазон в минутах
    const minutesRange = (t1 - t0) / 60000

    // количество минутных баров
    const data = this.data.slice(i0, i1)
    const minutesCount = data.length

    let dataSource

    // определяется уровень масштабирования
    if (minutesCount > 30000) {
      // месяцы
      this.xAxisFormat = d3.timeFormat("%b %Y")
      dataSource = this.data_1m
    } else if (minutesCount > 10000) {
      // недели
      this.xAxisFormat = d3.timeFormat("%e %b")
      dataSource = this.data_1w
    } else if (minutesCount > 1000) {
      // дни
      this.xAxisFormat = d3.timeFormat("%e %b")
      dataSource = this.data_1d
    } else if (minutesCount > 300) {
      // часы
      this.xAxisFormat = d3.timeFormat("%H:%M")
      dataSource = this.data_1h
    } else {
      this.xAxisFormat = d3.timeFormat("%H:%M")
      dataSource = this.data_10m
    }

    // TODO: BISECT
    const inRange = dataSource.filter((d) => ((d.idx >= i0) && (d.idx <= i1)))

    const ticks = []
    for (const bar of inRange) {
      // удаление последней метки, если новая метка близко к ней
      if (bar.idx - ticks[ticks.length - 1] < 5) {
        ticks.pop()
      }
      ticks.push(bar.idx)
    }

    return ticks
  }

  timeTickFormat(val, idx, ticksArray) {
    const tickVal = this.dateByIdx[val]
    return this.xAxisFormat(tickVal)
  }

  createAxes() {
    this.xAxis = (g, scale) => g
      .attr("transform", `translate(0,${this.height})`)
      .call(
        d3.axisBottom(scale)
          .tickSizeOuter(0)
          .tickValues(this.timeTickValues)
          .tickFormat((val) => this.timeTickFormat(val))
      )

    this.xAxisGrid = (g, scale) => g
      .attr("transform", `translate(0,${this.height})`)
      .call(
        d3.axisBottom(scale)
          .tickSizeOuter(0)
          .tickValues(this.timeTickValues)
          .tickSize(-this.height)
          .tickFormat("")
      )

    this.yAxisL = (g, scale) => g
      .attr("transform", `translate(0,0)`)
      .call(
        d3.axisLeft(scale)
          .ticks(5)
          .tickSizeOuter(0)
          .tickFormat(d => d.toFixed(2))
      )

    this.yAxisR = (g, scale) => g
      .attr("transform", `translate(${this.width},0)`)
      .call(
        d3.axisRight(scale)
          .ticks(5)
          .tickSizeOuter(0)
          .tickFormat(d => d.toFixed(2))
      )
  }

  drawGrid() {
    // сетка осей
    this.gxg = this.svg.append("g").classed("grid-x", true)
  }

  drawAxes() {
    // нарисовать оси
    this.gx = this.svg.append("g")
    this.gyl = this.svg.append("g")
    this.gyr = this.svg.append("g")
  }

  drawLine(data) {
    this.draw_price_line_for_data(data)
  }

  draw_trades(data, trades) {

    this.tradesLayer
      .selectAll("g.trade")
      .data(trades, d => d.idx)
      .join(

        // enter
        el => {
          const tradeEl = el
            .append('g')
            .classed("trade", true)

          // trade marker
          tradeEl
            .append("circle")
            .attr("r", 5)
            .attr("fill", d => d.side == "buy" ? "#080" : "#d00")
            .attr("stroke", "#fff")
            .attr("stroke-width", 2)

          // trade PnL
          tradeEl
            .append("text")
            .attr("dy", d => d.side == "buy" ? 20 : -20)
            .attr("dx", 0)
            .attr("font-size", 10)
            .attr("font-weight", "bold")
            .attr("text-anchor", "middle")
            .attr("fill", d => d.profit > 0 ? "#080" : "#d00")
            .text(d => {
              const n = Math.round(d.profit/100)
              return (n < 0 ? "" : "+") + n
            })

          return tradeEl
        },

        // update
        el => el
          .attr("transform", (d) => {
            // есть дата сделки, нужно положить её на шкалу
            const y0 = this.yScale(+d.price)
            const x0 = this.xScaleZoomed(d.idx)
            return `translate(${x0},${y0})`
          }),

        // exit
        el => el
          .remove()

      )
  }

  onAfterZoom() {
    // переопределяется в NavChart
  }

  onZoomed(event) {

    if (event) {
      this.xScaleZoomed = event.transform.rescaleX(this.xScale)
    } else {
      this.xScaleZoomed = this.xScale.copy()
    }

    const range = this.xScaleZoomed.domain()

    // Часть данных, входящая в отображаемый диапазон
    const dataZoomed = this.data.slice(Math.round(range[0]), Math.round(range[1]) + 1)

    this.draw_trades(dataZoomed, this.trades)

    this.drawLine(dataZoomed)

    // Перерисовать оси
    this.gx.call(this.xAxis, this.xScaleZoomed)
    this.gxg.call(this.xAxisGrid, this.xScaleZoomed)

    this.gyl.call(this.yAxisL, this.yScale)
    this.gyr.call(this.yAxisR, this.yScale)

    this.moveCrosshair(event)

    this.onAfterZoom()
  }

  onZoomEnd(event) {
    // Для обработки mouse up за пределами графика
    if (event && event.sourceEvent) {
      this.moveCrosshair(event)
    }
  }

  // Для более пиздатого зума с горизонтальным скроллом
  onWheeled(event) {
    // Какие-то параметры, влияющие на реакцию
    const scroll_speed = 0.8
    const zoom_speed_1 = 1.5
    const zoom_speed_2 = (event.deltaMode ? 120 : 1) / 500

    const dx = Math.abs(event.deltaX)
    const dy = Math.abs(event.deltaY)
    const t = d3.zoomTransform(event.target)

    // Чтобы Crosshair работал, когда курсор не двигали, но начали зумить
    this.cursorPos = d3.pointer(event)[0]
    this.cursorPosY = d3.pointer(event)[1]

    if (dx > dy) {
      // Horizontal Scroll
      let dx = event.deltaX * scroll_speed / t.k
      this.zoom.translateBy(this.chart, -dx, 0)
    } else {
      // Zoom
      let k = t.k * Math.pow(zoom_speed_1, -event.deltaY * zoom_speed_2)
      let p = d3.pointer(event)
      this.zoom.scaleTo(this.chart, k, p)
    }
    // Выключить скролл страницы
    return event.preventDefault && event.preventDefault()
  }

  // Положение курсора для crosshair
  moveCrosshair(event) {

    if (event) {
      // console.log(event)
      if (event.screenX !== undefined) {
        this.cursorPos = d3.pointer(event)[0]
        this.cursorPosY = d3.pointer(event)[1]
      }
      // Обработка перетаскивания (PAN)
      if (event.sourceEvent && event.sourceEvent.movementX !== undefined) {
        if (this.cursorPos !== null) {
          this.cursorPos += event.sourceEvent.movementX
        }
      }
      if (event.sourceEvent && event.sourceEvent.movementY !== undefined) {
        if (this.cursorPosY !== null) {
          this.cursorPosY += event.sourceEvent.movementY
        }
      }

      const x0 = this.xScaleZoomed.invert(this.cursorPos)
      const bar = this.data[Math.round(x0)]

      const y0 = this.yScale.invert(this.cursorPosY)
      // console.log(y0)
      this.crosshairY
        .attr("y1", this.cursorPosY)
        .attr("y2", this.cursorPosY)
      this.updateCrosshairLabelY(this.cursorPosY, y0.toFixed(2))

      if (this.cursorPos !== null && bar) {
        // Курсор над существующим интервалом
        const txt = this.xCrosshairLabelFormat(bar.date)
        this.crosshair
          .attr("x1", this.cursorPos)
          .attr("x2", this.cursorPos)
        this.updateCrosshairLabel(this.cursorPos, txt)
      } else {
        this.crosshair
          .attr("x1", -100)
          .attr("x2", -100)
        this.updateCrosshairLabel(-100000, "")
      }
    } else {
      // mouse out
      this.cursorPos = null
      this.crosshair
        .attr("x1", -100)
        .attr("x2", -100)
      this.crosshairY
        .attr("y1", -100)
        .attr("y2", -100)
      this.updateCrosshairLabel(-100000, "")
      this.updateCrosshairLabelY(-100000, "")
    }
  }

  setupZoom() {
    const extent = [[0, 0], [this.width, this.height]]

    // минимум N баров на экране
    const max_zoom = this.data.length / (this.width / 10)

    this.zoom = d3.zoom()
      .scaleExtent([1, max_zoom])
      .translateExtent(extent)
      .extent(extent)
      .on("zoom", (e) => { this.onZoomed(e) })
      .on("end", (e) => { this.onZoomEnd(e) })


    this.chart.call(this.zoom)
    this.chart.on("wheel.zoom", (e) => { this.onWheeled(e) })

    this.chart.on("mouseenter", (e) => { this.moveCrosshair(e) })
    this.chart.on('mousemove', (e) => { this.moveCrosshair(e) })
    this.chart.on("mouseleave", (e) => { if (!e.buttons) this.moveCrosshair(null) })

    this.onZoomed()
    this.onZoomEnd()
  }

  // Метод для изменения масштаба из навигационного графика
  zoomTo(scale, shift) {
    const transform = d3.zoomIdentity
      .scale(scale)
      .translate(shift, 0)
    this.zoom.transform(this.chart, transform)
  }

}