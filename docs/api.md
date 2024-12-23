# API

The JSON API is served under `/api/v1`. An interactive OpenAPI browser is available at
`/docs`, and the schema itself at `/openapi.json`; both can be turned off with
`VAULTR_DOCS_ENABLED=false`.

## Authentication

If [`VAULTR_API_TOKENS`](settings.md#authentication) is set, every request needs a
bearer token:

```bash
curl -H "Authorization: Bearer $VAULTR_TOKEN" localhost:8000/api/v1/projects
```

Without a valid token the API answers `401`.

## List projects

```
GET /api/v1/projects
```

```bash
curl -s localhost:8000/api/v1/projects
```

```json
{
  "projects": [
    {"name": "prod-myproject", "description": "Production", "vault_id": null},
    {"name": "test-myproject", "description": "Staging", "vault_id": null}
  ]
}
```

Passphrases are never part of the response.

## Encrypt a secret

```
POST /api/v1/encrypt
```

| Field           | Type   | Required | Description                                            |
| --------------- | ------ | -------- | ------------------------------------------------------ |
| `project`       | string | yes      | Name of a configured project.                           |
| `secret`        | string | yes      | The plaintext, encrypted verbatim.                      |
| `variable_name` | string | no       | Ansible variable name; adds `yaml_snippet` to the reply. |

```bash
curl -s localhost:8000/api/v1/encrypt \
  -H 'Content-Type: application/json' \
  -d '{"project": "prod-myproject", "secret": "s3cr3t", "variable_name": "db_password"}'
```

```json
{
  "project": "prod-myproject",
  "vault_id": null,
  "vault_text": "$ANSIBLE_VAULT;1.1;AES256\n6430...\n6161",
  "yaml_snippet": "db_password: !vault |\n          $ANSIBLE_VAULT;1.1;AES256\n          6430..."
}
```

`yaml_snippet` is `null` unless `variable_name` was given.

!!! warning "The plaintext is encrypted byte for byte"
    Unlike the web UI, the API adds and removes nothing. A trailing `\n` in `secret`
    ends up inside the encrypted value, which matters for things like SSH keys and API
    tokens. Strip it yourself if you do not want it.

### Errors

| Status | Meaning                                                      |
| ------ | ------------------------------------------------------------ |
| `401`  | Missing or invalid bearer token.                              |
| `404`  | Unknown project.                                              |
| `413`  | Secret larger than `VAULTR_MAX_SECRET_LENGTH`.                |
| `422`  | Malformed body, empty secret or invalid `variable_name`.      |

Errors carry a `detail` string:

```json
{"detail": "unknown project 'nope'"}
```

## Examples

=== "Shell"

    ```bash
    vaultr_encrypt() {
      curl -sf "$VAULTR_URL/api/v1/encrypt" \
        -H "Authorization: Bearer $VAULTR_TOKEN" \
        -H 'Content-Type: application/json' \
        -d "$(jq -n --arg p "$1" --arg s "$2" --arg n "$3" \
              '{project: $p, secret: $s, variable_name: $n}')" \
        | jq -r .yaml_snippet
    }

    vaultr_encrypt prod-myproject "$(printf %s "$SECRET")" db_password
    ```

=== "Python"

    ```python
    import httpx

    response = httpx.post(
        f"{VAULTR_URL}/api/v1/encrypt",
        headers={"Authorization": f"Bearer {VAULTR_TOKEN}"},
        json={
            "project": "prod-myproject",
            "secret": "s3cr3t",
            "variable_name": "db_password",
        },
    )
    response.raise_for_status()
    print(response.json()["yaml_snippet"])
    ```

## No decrypt endpoint

There is none, by design. Vaultr exists so that people who must not know a vault
passphrase can still produce encrypted values; giving them decryption back would undo
exactly that. Decrypt with `ansible-vault` where the passphrase legitimately lives.
