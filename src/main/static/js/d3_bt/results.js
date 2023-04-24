"use strict"


export class Results {

  print_results(results) {

    const $d3ChartInfo = document.querySelector('#d3_charts_results')

    let html = ""

    console.log(results)

    for (const key in results) {
        const value = results[key]
        html += `<div class="results-row">
            <div class="results-key">${key}</div>
            <div class="results-value">${value}</div>
        </div>`
    }

    $d3ChartInfo.innerHTML = `<div>
        <h3>Results</h3>
        ${html}
    </div>`
  }

  constructor(chartArea, results) {

    this.print_results(results)

  }

}
