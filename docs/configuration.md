# Projects

The configuration file lists the projects a user can encrypt for, and where each
project's Ansible Vault passphrase comes from. By default it is read from `config.yml`
in the working directory; point `VAULTR_CONFIG_FILE` elsewhere to change that.

```yaml
---
projects:
  - name: prod-myproject
    description: Production
    passphrase_env: VAULTR_PASSPHRASE_PROD

  - name: test-myproject
    description: Staging
    passphrase_file: /run/secrets/test-passphrase

  - name: legacy
    vault_id: legacy
    passphrase: not-for-production
```

The file is validated at startup. A malformed file, a duplicate project name or an
unresolvable passphrase stops the service from starting rather than failing on the
first request.

## Project fields

| Field             | Required | Description                                                        |
| ----------------- | -------- | ------------------------------------------------------------------ |
| `name`            | yes      | Unique identifier, shown in the UI and used in the API.             |
| `description`     | no       | Free text shown next to the name in the project picker.             |
| `vault_id`        | no       | Ansible vault ID; see [Vault IDs](#vault-ids).                      |
| `passphrase`      | one of   | The passphrase as a literal.                                        |
| `passphrase_env`  | one of   | Name of an environment variable holding the passphrase.             |
| `passphrase_file` | one of   | Path to a file holding the passphrase.                              |

`name` and `vault_id` accept letters, digits, dot, dash and underscore, up to 64
characters. Unknown fields are rejected, so a typo surfaces as a startup error instead
of being silently ignored.

## Passphrase sources

Exactly one of `passphrase`, `passphrase_env` or `passphrase_file` must be set. Giving
none, or more than one, is a configuration error.

=== "Environment"

    ```yaml
    projects:
      - name: prod-myproject
        passphrase_env: VAULTR_PASSPHRASE_PROD
    ```

    Good fit for container platforms that inject secrets as environment variables.

=== "File"

    ```yaml
    projects:
      - name: prod-myproject
        passphrase_file: /run/secrets/prod-passphrase
    ```

    Good fit for Docker or Kubernetes secrets mounted as files. A trailing newline is
    stripped, so a file written by an editor works as expected.

=== "Inline"

    ```yaml
    projects:
      - name: prod-myproject
        passphrase: not-for-production
    ```

    Convenient for local development. Avoid it in production: the passphrase ends up
    in the config file and therefore, sooner or later, in version control.

!!! warning "Passphrases are read once"
    Every passphrase is resolved at startup. Rotating one means restarting the
    service.

## Vault IDs

Without `vault_id`, Vaultr emits the standard header that every Ansible release
understands:

```
$ANSIBLE_VAULT;1.1;AES256
```

Setting `vault_id` emits a labelled `1.2` header instead, which records which
passphrase the value belongs to:

```
$ANSIBLE_VAULT;1.2;AES256;prod
```

Use it when your playbooks already pass `--vault-id prod@...`. If you are not sure,
leave it unset.
