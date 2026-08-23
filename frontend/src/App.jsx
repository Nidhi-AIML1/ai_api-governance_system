import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts'

import './App.css'

const requestData = [
  { time: '10 AM', requests: 400 },
  { time: '11 AM', requests: 650 },
  { time: '12 PM', requests: 500 },
  { time: '1 PM', requests: 900 },
  { time: '2 PM', requests: 750 },
  { time: '3 PM', requests: 1100 },
  { time: '4 PM', requests: 950 }
]

function App() {
  return (
    <div className="app">

      {/* Sidebar */}
      <aside className="sidebar">
        <h2>API Governance</h2>

        <nav>
          <div className="nav-item active">Dashboard</div>
          <div className="nav-item">APIs</div>
          <div className="nav-item">Microservices</div>
          <div className="nav-item">Monitoring</div>
          <div className="nav-item">Governance</div>
          <div className="nav-item">Security</div>
          <div className="nav-item">AI Insights</div>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="main-content">

        {/* Header */}
        <header className="header">
          <div>
            <h1>API & Microservice Governance</h1>
            <p>Monitor, analyze and govern your API ecosystem</p>
          </div>

          <div className="profile">
            👤 Admin
          </div>
        </header>

        {/* Dashboard */}
        <section className="dashboard">

          <h2>Overview</h2>

          {/* Cards */}
          <div className="cards">

            <div className="card">
              <p>Total APIs</p>
              <h3>128</h3>
            </div>

            <div className="card">
              <p>Healthy APIs</p>
              <h3>103</h3>
            </div>

            <div className="card">
              <p>At Risk</p>
              <h3>18</h3>
            </div>

            <div className="card">
              <p>Critical</p>
              <h3>7</h3>
            </div>

          </div>

          {/* Temporary chart area */}
          <div className="chart-section">
           <div className="chart-box">
  <h3>API Request Traffic</h3>

  <ResponsiveContainer width="100%" height={190}>
    <LineChart data={requestData}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="time" />
      <YAxis />
      <Tooltip />

      <Line
        type="monotone"
        dataKey="requests"
        stroke="#2563eb"
        strokeWidth={3}
      />
    </LineChart>
  </ResponsiveContainer>
</div>

            <div className="chart-box">
              <h3>API Health</h3>
              <div className="placeholder">
                Health chart will come here
              </div>
            </div>

          </div>

          {/* Table */}
          <div className="table-section">

            <h3>API Monitoring</h3>

            <table>
              <thead>
                <tr>
                  <th>API Name</th>
                  <th>Service</th>
                  <th>Requests</th>
                  <th>Errors</th>
                  <th>Response Time</th>
                  <th>Status</th>
                </tr>
              </thead>

              <tbody>
                <tr>
                  <td>/users</td>
                  <td>User Service</td>
                  <td>1200</td>
                  <td>20</td>
                  <td>180 ms</td>
                  <td>Healthy</td>
                </tr>

                <tr>
                  <td>/orders</td>
                  <td>Order Service</td>
                  <td>2500</td>
                  <td>45</td>
                  <td>220 ms</td>
                  <td>Healthy</td>
                </tr>

                <tr>
                  <td>/payment</td>
                  <td>Payment Service</td>
                  <td>3200</td>
                  <td>180</td>
                  <td>620 ms</td>
                  <td>Critical</td>
                </tr>
              </tbody>
            </table>

          </div>

        </section>

      </main>

    </div>
  )
}

export default App