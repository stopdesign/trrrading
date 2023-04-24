"use strict"

import {React, html, useEffect, useState} from "./deps.js";
import { ChartManager } from "./d3_bt/chart_manager.js";



const Orders = ({curResult, curStrategy}) => {

  // Создание графика при старте
  useEffect(() => {

    console.error("create a chart");

  }, []);

  // const fetchOrders = (curResult, curStrategy) => {
  //   fetch(`/bt/events?result=${curResult}&strategy=${curStrategy}`)
  //     .then(function (response) {
  //       return response.json();
  //     })
  //     .then(function (res_json) {
  //       // Перезаписывать только при изменениях
  //       if (JSON.stringify(orders) !== JSON.stringify(res_json)) {
  //         setOrders(res_json);
  //       }
  //     });
  // }

  // // Изменился symbol
  useEffect(() => {
    // console.log("on result or strategy change", curResult, curStrategy)
    const chartDiv = document.getElementById("d3_charts_container");
    chartDiv.innerHTML = ""

    const chart = new ChartManager(chartDiv)

    if (curResult && curStrategy) {

      // console.log("show chart", curResult, curStrategy);

      document.querySelector('#d3_charts_results').innerHTML = "";
      document.querySelector('#d3_charts_info').innerHTML = "";

      chart.run(curResult, curStrategy)

      // fetchOrders(curResult, curStrategy);

      chartDiv.style.display = '';
    } else {
      // Скрыть график
      chartDiv.style.display = 'none';
    }
  }, [curStrategy]);

  return html`
      <div className="orders_and_chart">
          <div id="d3_charts_container"></div>
          <div id="d3_charts_info"></div>
          <div id="d3_charts_results"></div>
      </div>
  `;
}


export default Orders;
