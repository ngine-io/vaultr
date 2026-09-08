# Vaultr

[![Python tests](https://github.com/ngine-io/vaultr/actions/workflows/tests.yml/badge.svg)](https://github.com/ngine-io/vaultr/actions/workflows/tests.yml)
![python versions](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)

Encrypt secrets into [Ansible Vault](https://docs.ansible.com/ansible/latest/vault_guide/)
strings through a web UI, a JSON API or MCP, without ever handing out the vault
passphrase.

Projects and their passphrases are configured server side. A user picks a project,
submits a secret, and gets the encrypted string back. An already encrypted secret can
also be re-encrypted from one project into another, for example promoting a staging
value into production. Either way the plaintext never leaves the server, and there is
no decryption endpoint.

📖 **[Documentation](https://ngine-io.github.io/vaultr/)**

## Quickstart

```bash
uv sync
npm ci && npm run build          # collect the Tabler stylesheet and scripts
cp .env.example .env             # set the project passphrases
uv run vaultr-ngine
```

Open <http://localhost:8000> for the UI, <http://localhost:8000/api> for the API docs,
or point an MCP client at <http://localhost:8000/mcp>.

## Container

```bash
docker run --rm -p 8000:8000 \
  -v ./config.yml:/app/config.yml:ro \
  -e VAULTR_PASSPHRASE_PROD=... \
  ghcr.io/ngine-io/vaultr:main
```

## Configuration

```yaml
projects:
  - name: prod-myproject
    description: Production
    passphrase_env: VAULTR_PASSPHRASE_PROD
    reencrypt_targets: []          # production secrets may not leave

  - name: test-myproject
    description: Staging
    passphrase_file: /run/secrets/test-passphrase
    reencrypt_targets:             # staging values may be promoted
      - prod-myproject
```

Re-encrypting decrypts with the source project's passphrase, so anyone who knows the
target passphrase learns the secret. `reencrypt_targets` limits where a project's
secrets may go; leave it unset to allow any target, or set
`VAULTR_REENCRYPT_ENABLED=false` to turn the feature off entirely.

## API

```bash
curl -s localhost:8000/api/v1/encrypt \
  -H 'Content-Type: application/json' \
  -d '{"project": "prod-myproject", "secret": "s3cr3t", "variable_name": "db_password"}'

curl -s localhost:8000/api/v1/reencrypt \
  -H 'Content-Type: application/json' \
  -d '{"source_project": "test-myproject", "target_project": "prod-myproject",
       "vault_text": "$ANSIBLE_VAULT;1.1;AES256\n6430..."}'
```

## MCP

Agents encrypt and re-encrypt through the built-in
[MCP server](https://ngine-io.github.io/vaultr/mcp/):

```bash
claude mcp add --transport http vaultr http://localhost:8000/mcp
```

## License

Apache License 2.0, see [LICENSE](LICENSE).
