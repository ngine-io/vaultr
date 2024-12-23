# Web UI

The UI lives at `/`. It is server rendered, styled with
[Tailwind CSS](https://tailwindcss.com) and [daisyUI](https://daisyui.com), and
enhanced with [htmx](https://htmx.org) so the result appears without a page reload.

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

## Copy buttons

The copy buttons use the clipboard API, which browsers only allow on `https://` or
`localhost`. Over plain HTTP the button selects the text instead so you can copy it
with ++ctrl+c++.

## Without JavaScript

The form is a plain HTML `POST`. Without htmx the browser submits it normally and the
whole page is re-rendered with the result. Everything works, just with a full reload.
