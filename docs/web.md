# Web UI

The UI lives at `/`. It is server rendered, built with [Tabler](https://tabler.io),
and enhanced with [htmx](https://htmx.org) so the result appears without a page
reload.

## Encrypting

1. **Project** — pick one of the configured projects. The passphrase behind it is
   never shown.
2. **Secret** — paste the value to encrypt. Multi-line input is supported.
3. **Variable name** *(optional)* — an Ansible variable name. When set, you also get a
   ready to paste YAML block.

Press **Encrypt** and copy the result.

## What you get

Without a variable name, the raw vault string:

```
$ANSIBLE_VAULT;1.1;AES256
64303339626162323866376635623039363538366233333032643330383435303262643433626666
6231623062383938383539626262633839623034356539350a363035643931636433333535353564
```

With `db_password` as the variable name, additionally the block that
`ansible-vault encrypt_string --stdin-name db_password` produces:

```yaml
db_password: !vault |
          $ANSIBLE_VAULT;1.1;AES256
          64303339626162323866376635623039363538366233333032643330383435303262643433626666
          6231623062383938383539626262633839623034356539350a363035643931636433333535353564
```

Paste it straight into `group_vars/` or `host_vars/`.

## Input handling

The browser textarea submits `\r\n` line endings and leaves a trailing newline behind,
neither of which is usually part of the secret. The UI therefore normalises line
endings to `\n` and removes trailing newlines before encrypting. Leading and inner
whitespace is preserved exactly.

!!! note
    The [API](api.md) does neither, and encrypts the plaintext byte for byte. Use it
    when the exact bytes matter, for example for a certificate key.

## Re-encrypting a secret

The **Re-encrypt** page moves a secret that is already encrypted from one project to
another, for example promoting a value from staging into production. You never see the
plaintext: Vaultr decrypts it with the source project's passphrase and immediately
re-encrypts it with the target's.

1. **From project** — the project the secret is encrypted for today.
2. **To project** — the project it should be encrypted for instead.
3. **Encrypted secret** — paste the `$ANSIBLE_VAULT` block, or the whole
   `key: !vault |` snippet straight out of your `group_vars`. The indentation is
   handled for you.
4. **Variable name** *(optional)* — as on the encryption page.

If the secret does not belong to the project you picked as the source, you get an
error saying so rather than a result; that is the expected way to discover you chose
the wrong source.

The page is hidden and both routes return `404` when
`VAULTR_REENCRYPT_ENABLED=false`.

!!! warning "Re-encryption is privileged"
    Whoever can move a secret out of a project can read it, if they know the target
    project's passphrase. Restrict it with `reencrypt_targets`; see
    [Security](security.md#re-encryption).

## Copy buttons

The copy buttons use the clipboard API, which browsers only allow on `https://` or
`localhost`. Over plain HTTP the button selects the text instead so you can copy it
with ++ctrl+c++.

## Without JavaScript

The form is a plain HTML `POST`. Without htmx the browser submits it normally and the
whole page is re-rendered with the result. Everything works, just with a full reload.
