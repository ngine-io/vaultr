# Vaultr

Encrypt secrets into [Ansible Vault](https://docs.ansible.com/ansible/latest/vault_guide/)
strings through a web UI or a JSON API, without ever handing out the vault passphrase.

Projects and their passphrases are configured server side. A user picks a project,
submits a secret, and gets the encrypted string back. They never learn the passphrase,
and there is no decryption endpoint.

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

  - name: test-myproject
    description: Staging
    passphrase_file: /run/secrets/test-passphrase
```

## Re-encrypt between projects

Promote an already encrypted secret from one project to another without seeing the
plaintext:

```bash
curl -s localhost:8000/api/v1/reencrypt \
  -H 'Content-Type: application/json' \
  -d '{"source_project": "test-myproject", "target_project": "prod-myproject",
       "vault_text": "$ANSIBLE_VAULT;1.1;AES256\n6430..."}'
```

Restrict where secrets may be moved with `reencrypt_targets`, or turn the feature off
with `VAULTR_REENCRYPT_ENABLED=false`.

## MCP

Agents can encrypt through the built-in [MCP server](https://ngine-io.github.io/vaultr/mcp/):

```bash
claude mcp add --transport http vaultr http://localhost:8000/mcp
```

## API

```bash
curl -s localhost:8000/api/v1/encrypt \
  -H 'Content-Type: application/json' \
  -d '{"project": "prod-myproject", "secret": "s3cr3t", "variable_name": "db_password"}'
```

## License

Apache License 2.0, see [LICENSE](LICENSE).
