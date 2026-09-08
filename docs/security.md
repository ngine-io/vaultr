# Security

Vaultr holds vault passphrases and handles other people's plaintext secrets. This page
describes what it does about that, and what it expects from you.

## Threat model

Vaultr assumes its users are trusted enough to *write* encrypted values for a project,
but not trusted enough to *know* the project's passphrase.

That is a real distinction, but a narrow one. Anyone who can reach the service can
produce a valid vault string for any configured project, and Ansible will decrypt and
use it. Treat access to Vaultr as the permission to inject values into that project's
inventory.

!!! danger "Authenticate it"
    An open Vaultr instance lets anyone forge values for every project it knows about.
    Set [`VAULTR_API_TOKENS`](settings.md#authentication) or put it behind a proxy that
    authenticates. Vaultr logs a warning at startup when neither is in place.

## What Vaultr does

**No shell.** Encryption calls Ansible's `VaultLib` in process. Nothing is passed to a
shell, written to a temporary file or placed in an argument vector, so no plaintext is
visible in `/proc`, in a shell history or to another process on the host.

**No storage.** Secrets exist only for the duration of the request. Nothing is written
to disk, no session, no cache. Responses carrying ciphertext are sent with
`Cache-Control: no-store`.

**No leaking into logs.** Passphrases are held in `SecretStr`, so they do not appear in
a log line or a stack frame. Loguru's variable rendering in tracebacks is switched off.
The submitted plaintext is never logged, and the UI does not echo it back into the
form, keeping it out of the browser's page cache and back button.

**No decryption.** There is no endpoint that turns a vault string back into plaintext.
Re-encryption decrypts internally but never returns the plaintext; see
[Re-encryption](#re-encryption) for what that does and does not protect.

**Fail closed at startup.** The configuration and every passphrase are resolved before
the first request. A missing environment variable or an unreadable secret file stops
the service instead of producing confusing failures later.

**Input validation.** Project names and vault IDs are restricted so they cannot corrupt
the vault header. Variable names must be valid Ansible identifiers, which prevents
injecting arbitrary YAML into the generated snippet. Plaintext size is capped by
`VAULTR_MAX_SECRET_LENGTH`.

**Constant time token comparison.** Bearer tokens are compared with
`secrets.compare_digest` against every configured token, so neither the value nor the
position of the matching token leaks through timing.

**Security headers.** Every response carries `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` and a Content Security Policy
that allows scripts and styles from the service's own origin only. All frontend assets
are served locally; no CDN is involved.

**Non-root container.** The image runs as UID 1000 and contains no build tooling.

## What you must do

- **Terminate TLS.** Plaintext secrets travel in the request body. Never expose Vaultr
  over plain HTTP outside of localhost.
- **Authenticate.** See above.
- **Keep passphrases out of the config file.** Prefer `passphrase_env` or
  `passphrase_file` so `config.yml` can live in version control safely.
- **Restrict who can reach it.** Network policy, VPN or an authenticating proxy.
- **Rotate deliberately.** Passphrases are read once at startup; rotating one means
  restarting the service and re-encrypting the values that used it.

## Re-encryption

[Re-encryption](api.md#re-encrypt-a-secret) moves an encrypted secret from one
project's passphrase to another's. It is the one place where Vaultr decrypts, so it
deserves its own analysis.

The plaintext never leaves the process. It exists only between the decrypt and the
re-encrypt call, is never returned, logged or stored, and the result is sent with
`Cache-Control: no-store`.

!!! danger "It is a decryption oracle for anyone who holds a target passphrase"
    Re-encrypting a secret out of a project you cannot read, into a project whose
    passphrase you *do* know, and then decrypting the result with `ansible-vault`,
    recovers the original secret.

    This is inherent to the feature, not a flaw in the implementation. It means the
    ability to re-encrypt out of a project is equivalent to the ability to read that
    project's secrets, for anyone who legitimately holds any other project's
    passphrase, such as a developer who knows the staging passphrase.

Re-encryption is offered over the web UI, the [HTTP API](api.md#re-encrypt-a-secret)
and as the [`reencrypt_secret` MCP tool](mcp.md#reencrypt_secret). The MCP surface
widens the exposure: an agent can be steered by a prompt injection in content it reads,
so if agents have a token, prefer constraining the flows below rather than relying on
the tool description.

Three controls are available, in order of bluntness:

1. **Turn it off.** `VAULTR_REENCRYPT_ENABLED=false` removes the API endpoint, the UI
   page and the MCP tool entirely.
2. **Restrict the direction.** `reencrypt_targets` on a project lists the only
   projects its secrets may be moved into. An empty list forbids all of them.
   Promotion usually flows one way, so allowing staging into production while
   forbidding the reverse matches how most teams work:

    ```yaml
    projects:
      - name: prod-myproject
        passphrase_env: VAULTR_PASSPHRASE_PROD
        reencrypt_targets: []          # nothing may leave production

      - name: test-myproject
        passphrase_env: VAULTR_PASSPHRASE_TEST
        reencrypt_targets:
          - prod-myproject             # staging may be promoted into production
    ```

3. **Restrict who can reach it**, with `VAULTR_API_TOKENS` or an authenticating proxy,
   as for everything else.

The allowlist is checked before anything is decrypted, so a refused combination does
not reveal whether the input was even a valid secret.

## Cryptography

Vaultr does not implement any cryptography. It calls
`ansible.parsing.vault.VaultLib`, the same code `ansible-vault` itself uses, so output
is byte compatible with the format Ansible expects: AES-256-CTR with a PBKDF2 derived
key and an HMAC-SHA256 tag, salted per encryption.

The test suite decrypts every generated string with a plain `VaultLib` to prove the
round trip, and asserts that two encryptions of the same plaintext differ.

## Reporting a vulnerability

Report security issues privately through
[GitHub security advisories](https://github.com/ngine-io/vaultr/security/advisories/new)
rather than in a public issue.
