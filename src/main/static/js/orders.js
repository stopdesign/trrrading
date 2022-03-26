import {html, React} from "./deps.js";


const Order = ({ data }) => {

  const clickMe = (aaa) => {
    console.log(aaa);
  }

  return (
    html`
        <li onClick=${() => clickMe(data.symbol)}>
            <span>${data.symbol}</span>,
            amnt: <span>${data.amount}</span>
        </li>`
  );
}


const Orders = ({ account }) => {
  const [orders, setOrders] = React.useState([]);

  React.useEffect(() => {
    const interval = setInterval(() => fetchOrders(), 5000);
    return () => {
      clearInterval(interval);
    };
  }, []);

  const fetchOrders = () => {
    fetch('http://127.0.0.1:8000/dash/orders?account=' + account)
      .then(function (response) {
        return response.json();
      })
      .then(function (res_json) {
        setOrders(res_json);
      });
  }

  React.useEffect(() => {
    fetchOrders()
  }, []);

  return (
    html`
        <div>
            <h4>Orders</h4>
            <ul>
                ${orders.map((pos, i) => html`<${Order} data=${pos} key=${i} />`)}
            </ul>
        </div>`
  );
}


export default Orders;
