# Settings

Runtime behaviour is configured through environment variables, all prefixed with
`VAULTR_`. A `.env` file in the working directory is read as well, which is handy for
local development; see `.env.example`.

| Variable                | Default      | Description                                                          |
| ----------------------- | ------------ | -------------------------------------------------------------------- |
| `VAULTR_APP_NAME`       | `Vaultr`     | Title shown in the UI and the OpenAPI schema.                         |
| `VAULTR_CONFIG_FILE`    | `config.yml` | Path to the [project configuration](configuration.md).                |
| `VAULTR_API_TOKENS`     | empty        | Comma separated bearer tokens. Empty disables authentication.         |
| `VAULTR_ROOT_PATH`      | empty        | Mount prefix behind a reverse proxy, e.g. `/vaultr`.                  |
| `VAULTR_LOG_LEVEL`      | `INFO`       | `DEBUG`, `INFO`, `WARNING` or `ERROR`.                                |
| `VAULTR_LOG_JSON`       | `false`      | Emit structured JSON logs instead of human readable ones.             |
| `VAULTR_MAX_SECRET_LENGTH` | `65536`   | Largest accepted plaintext, in characters.                            |
| `VAULTR_DOCS_ENABLED`   | `true`       | Serve `/docs` and `/openapi.json`.                                    |

The container image additionally sets `VAULTR_CONFIG_FILE=/app/config.yml`.

## Authentication

```bash
VAULTR_API_TOKENS=token-for-ci,token-for-alice
```

Any configured token grants full access to both the UI and the API. Tokens are
compared in constant time. With no tokens set, the service is open and logs a warning
at startup.

For anything beyond a handful of tokens, put Vaultr behind a proxy that does real
authentication and leave `VAULTR_API_TOKENS` empty.

## Logging

Vaultr never logs the submitted plaintext or a project passphrase, and loguru's
variable rendering in tracebacks is disabled so an unexpected exception cannot spill
them either.

Set `VAULTR_LOG_JSON=true` to emit one JSON object per line for log shippers.
