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
