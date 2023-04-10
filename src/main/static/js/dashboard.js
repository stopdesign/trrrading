import { html, useState } from "./deps.js"
import Positions from "./positions.js"
import Account from "./account.js"
import Orders from "./orders.js"
import Health from "./health.js"


const Dashboard = ({ accounts }) => {

  const [symbol, setSymbol] = useState()
  const [account, setAccount] = useState(accounts[0])

  return html`
      <div className="dashboard">
          <div className="left_sidebar">
              <div className="health_panel">
                  <h4>Accounts</h4>
                  <div className="accounts">
                    ${accounts.map((a) => html`
                      <span onClick="${ () => setAccount(a) }">${a.uid}</span>
                    `)}
                  </div>
              </div>
              <${Account} account=${account.id} account_uid=${account.uid} key="2"/>
              <${Positions} account=${account.id} symbol=${symbol} setSymbol=${setSymbol} key="3"/>
          </div>
          <div className="main">
              <${Orders} account=${account.id} symbol=${symbol}/>
          </div>
      </div>
  `
}

export default Dashboard
