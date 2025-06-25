# Development Report

## Metrics

The project tracks the following runtime metrics:

- **TPS (Transactions Per Second)**: Rate of processing requests.
- **Average Latency**: Mean response time between input and response.
- **Guardrail Rejects**: Count of requests blocked by guardrail policies.
- **Calendar Errors**: Number of failures during calendar operations.

Metrics are automatically calculated after each call and saved as Markdown
reports in the `reports/` directory. A demo call will generate a report for
review using the same metrics.
