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
| `reencrypt_targets` | no     | Projects this one's secrets may be moved into; see below.           |
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

## Re-encryption targets

[Re-encryption](web.md#re-encrypting-a-secret) decrypts a secret with one project's
passphrase and re-encrypts it with another's. `reencrypt_targets` lists which target
projects that is permitted for:

```yaml
projects:
  - name: prod-myproject
    passphrase_env: VAULTR_PASSPHRASE_PROD
    reencrypt_targets: []          # nothing may be moved out of production

  - name: test-myproject
    passphrase_env: VAULTR_PASSPHRASE_TEST
    reencrypt_targets:
      - prod-myproject             # staging may be promoted into production
```

| Value            | Meaning                                                  |
| ---------------- | -------------------------------------------------------- |
| unset (default)  | The secret may be re-encrypted into any project.          |
| a list of names  | Only those projects are allowed as a target.              |
| `[]`             | The secret may not be re-encrypted into anything.         |

Every name must match a configured project, so a typo is a startup error rather than a
flow that silently stops working. The restriction is one directional: it says where
this project's secrets may go, not what may be moved into it.

!!! warning "This is an access control decision, not a convenience setting"
    Being able to re-encrypt out of a project is equivalent to being able to read it,
    for anyone who knows the target project's passphrase. See
    [Security](security.md#re-encryption).

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
