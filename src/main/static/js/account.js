import {html, React} from "./deps.js";


const Account = ({account}) => {
  const [values, setValues] = React.useState({});

  React.useEffect(() => {
    const interval = setInterval(() => fetchData(), 5000);
    return () => {
      clearInterval(interval);
    };
  }, []);

  const fetchData = () => {
    fetch('http://127.0.0.1:8000/dash/account?account=' + account)
      .then(function (response) {
        return response.json();
      })
      .then(function (res_json) {
        setValues(res_json);
      });
  }

  React.useEffect(() => {
    fetchData()
  }, []);

  return html`
      <div className="account_panel">
          <p>Account: ${values.uid}</p>
          <p>Net Value: ${values["net_value"]}</p>
      </div>
  `;
}


export default Account;
