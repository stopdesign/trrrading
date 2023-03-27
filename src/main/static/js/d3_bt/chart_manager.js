"use strict"

// @ts-ignore
import * as d3 from "https://cdn.skypack.dev/d3@7"

import { PriceChart } from "./price_chart.js"
import { PerformanceChart } from "./performance_chart.js"
import { NavChart } from "./nav_chart.js"
import { PriceAroundTrades } from "./price_around_trades.js"

export class ChartManager {

  constructor(chartArea) {

    this.chartArea = chartArea

  }

  parseDate = d3.timeParse('%Y-%m-%d %H:%M:%S')

  async run(bt_uid, symbol) {

    // let [data, trades, stats] = await Promise.all([d3.csv('data.csv'), d3.csv('trades.csv'), d3.csv('stats.csv')])

    const base = "http://127.0.0.1:8000"

    let ohlc = await d3.json(`${base}/bt/raw?symbol=${bt_uid}-${symbol}`);
    let events = await d3.json(`${base}/bt/events?result=${bt_uid}&strategy=${symbol}`);

    console.log([...events])

    // Хочу посчитать все параметры на фронте,
    // т.к. это позволит использовать график для любых бэктестов,
    // которые выдают список сделок.
    // Плюс это кроссвалидация результата.

    // {
    //   "date": "2021-12-27 14:34:00", "symbol": "URA.ARCA", "open": 24.635,
    //   "high": 24.71, "low": 24.635, "close": 24.68, "volume": 2190.0,
    //   "rth": true, "n1": null, "n2": null, "ts": 1640615640, "profit": 0,
    //   "strategy": "HullMa"
    // },

    for (var i in ohlc) {
      ohlc[i]["idx"] = +i
      ohlc[i]["date"] = new Date(ohlc[i]["ts"] * 1000)
      ohlc[i]["time"] = ohlc[i]["ts"] * 1000
    }

    // for (const idx in history.t) {
    //   ohlc.push({
    //     date: new Date(history.t[idx] * 1000),
    //     time: history.t[idx] * 1000,
    //     idx: +idx,
    //     open: +history.o[idx],
    //     high: +history.h[idx],
    //     low: +history.l[idx],
    //     close: +history.c[idx],
    //   })
    // }

    // Парсинг формата TV
    // let ohlc = []
    // for (const idx in history.t) {
    //   ohlc.push({
    //     date: new Date(history.t[idx] * 1000),
    //     time: history.t[idx] * 1000,
    //     idx: +idx,
    //     open: +history.o[idx],
    //     high: +history.h[idx],
    //     low: +history.l[idx],
    //     close: +history.c[idx],
    //   })
    // }

    // Пройтись по двум массивам одновременно.
    // Цикл по ценам. Как только дата текущей сделки становится
    // меньше или равна дате из цен — обработать сделку и убрать из списка.
    // В начале проверить, что дата первой сделки больше даты первой цены.
    // В конце проверить, что сделок не осталось.
    // Получится два массива одинаковой размерности: цены и депозит.

    let trades_1 = []
    const trade_size = 100000.0  // условные деньги
    const initial_cash = 100000.0
    let realized_pnl = 0
    let position = 0
    let cash = trade_size

    let trade = events.shift()
    for (const bar of ohlc) {

      if (trade) {
        // console.info(new Date(bar.time))
        if (trade.time * 1000 < bar.time) {
          console.error(trade.time, bar.time)
          // console.error(new Date(bar.time))
          trade = events.shift()
        }
        if (trade.time * 1000 == bar.time) {
          // обработать сделку
          // ...

          const p = +trade.price
          let trade_pnl = 0

          if (position > 0) {
            // закрыть long
            trade_pnl = position * p + cash
          }
          if (position < 0) {
            // закрыть short
            trade_pnl = cash + position * p
          }

          position = 0
          cash = 0

          let amount = trade_size / p  // может быть дробным, но это норм

          // открыть новую
          if (trade.side == "buy") {
            position = amount
            cash = -amount * p  // потрачено на покупку
          }
          if (trade.side == "sell") {
            position = -amount
            cash = amount * p   // получено с продажи
          }

          if (trade.signal == "close") {
            position = 0
          }

          realized_pnl += trade_pnl

          trades_1.push({
            date: new Date(trade.time * 1000),
            time: trade.time * 1000,
            id: trade.id,
            side: trade.side,
            price: +trade.price,
            profit: trade.profit,
          })

          // выбрать следующую сделку
          trade = events.shift()
        }
      } else {
        // больше нет сделок
      }

      let unrealized_pnl = 0
      if (position > 0) {
        // закрыть long
        unrealized_pnl = position * bar["close"] + cash
      }
      if (position < 0) {
        // закрыть short
        unrealized_pnl = cash + position * bar["close"]
      }

      bar["pnl"] = Math.round(realized_pnl / trade_size * 10000) / 100
      bar["net_value"] = initial_cash + realized_pnl + unrealized_pnl
      bar["drawdown"] = 0

    }


    // console.info(trades_1)
    // console.info(ohlc)

    // let idx = 0
    // for (const trade of trades) {
    //   idx += 10
    //   trade.idx = idx
    //   trade.date = this.parseDate(trade.date)
    // }

    // data = data.map((d, idx) => ({
    //   date: this.parseDate(d.date),
    //   time: this.parseDate(d.date).getTime(),
    //   idx: idx,
    //   open: +d.open,
    //   high: +d.high,
    //   low: +d.low,
    //   close: +d.close,
    // }))

    // let max_value = 0
    // stats = stats.map((d, idx) => {
    //   const value = +d.net_value;
    //   max_value = Math.max(max_value, value);
    //   const drawdown = max_value - value;
    //   return {
    //     date: this.parseDate(d.date),
    //     time: this.parseDate(d.date).getTime(),
    //     idx: idx,
    //     net_value: value,
    //     drawdown: drawdown,
    //     // drawdown: +d.drawdown,
    //   }
    // })

    this.priceChart = new PriceChart(this.chartArea, ohlc, trades_1)

    this.performanceChart = new PerformanceChart(this.chartArea, ohlc)

    // this.priceAroundTrades = new PriceAroundTrades(this.chartArea, ohlc, trades_1)

    this.navChart = new NavChart(this.chartArea, this.priceChart, this.performanceChart)

  }

}
