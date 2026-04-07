const express = require("express");

const app = express();
const PORT = 3000;

const client = require("prom-client");

// collect default metrics provided by library
const collectedDefaultMetrics = client.collectDefaultMetrics;
collectedDefaultMetrics({ timeout: 5000 })

// metrics to get request count
const httpRequestsTotal = new client.Counter({
  name: "http_request_connection_total",
  help: "Total number of http request"
})

// metrics for duration of request
const httpRequestDurationSeconds = new client.Histogram({
  name: " ",
  help: "Duration of Http requests in seconds",
  buckets: [0.1, 0.5, 2, 5, 10]
})

// expose all the metrics date at /metrics endpoint
// it have many other metrics that we have created
app.get("/metrics", async (req, res) => {
  res.set("Content-Type", client.register.contentType);
  res.end(await client.register.metrics());
})

app.get('/', function (req, res) {
  // Simulate sleep for a random number of milliseconds
  var start = new Date()
  var simulateTime = Math.floor(Math.random() * (10000 - 500 + 1) + 500)

  // wait for random delay and count request duration in metrics
  setTimeout(function (argument) {
    // Simulate execution time
    var end = new Date() - start
    httpRequestDurationSeconds.observe(end / 1000); //convert to seconds
  }, simulateTime)

  // increment number of request metrics
  httpRequestsTotal.inc();
  res.send("Application is running");
});

app.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});