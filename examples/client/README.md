# Client examples

How clients authenticate to the OIDC-protected server from
[`../README.md`](../README.md). The token is the client's bearer credential —
Hindsight reads it as `api_key`. See [../../docs/client-configuration.md](../../docs/client-configuration.md).

| File | For |
|---|---|
| [`curl.sh`](curl.sh) | Raw HTTP — password grant + a call |
| [`python_client.py`](python_client.py) | Interactive user via the Python SDK |
| [`agent_client_credentials.py`](agent_client_credentials.py) | A background agent (machine-to-machine) with auto-refresh |

All target the example stack (`issuer http://localhost:8280`, API
`http://localhost:8893`).
