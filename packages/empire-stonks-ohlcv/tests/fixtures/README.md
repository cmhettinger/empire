# Provider fixture policy

Provider parser fixtures live under:

```text
tests/fixtures/<provider>/<source_code>/
```

`<provider>` is the lowercase database provider code. `<source_code>` is one of
the production identities exported by `empire_stonks_ohlcv.source_conventions`.
Do not create a fixture directory until repository format evidence or the
corresponding provider source contract documents the endpoint or file, raw
format, native identity fields, and observed OHLCV fields.

Every raw fixture payload must have a `<payload_file>.fixture.json` sidecar
that conforms to `manifest.schema.json`. The sidecar records the repository source
contract used as the format reference, whether the payload is a sanitized
excerpt or was constructed from documented syntax, its exact checksum and
size, the sanitization performed, and the parser cases it exists to cover.

## Content rules

- Commit the smallest payload that preserves the provider's real field names,
  nesting, delimiters, quoting, null representation, case, and numeric text.
- Keep each raw or compressed payload at or below 64 KiB. Large historical
  behavior belongs in generated test data, not a copied provider archive.
- Include only rows required for a happy path or named parser edge case. Do not
  preserve unrelated enrichment, fundamentals, or descriptive metadata.
- Use fixed fictional identities where replacing a real identity does not
  change parser behavior. Preserve exact provider-native case and punctuation
  when those are the behavior under test.
- Remove credentials, authentication material, cookies, signed or query-bearing
  URLs, account identifiers, request headers, local paths, and unneeded personal
  or proprietary data. A placeholder must not resemble a working secret.
- Never generate committed fixtures by calling a live provider during tests.
  Acquisition tests use injected transports; parser tests read committed bytes.
- Keep payload bytes deterministic. Use UTF-8 and LF for text unless the source
  contract specifically requires another encoding or newline convention.
- Compressed fixtures are allowed only when compression is part of the selected
  source contract. The manifest size and checksum describe the committed bytes;
  reviewers must also inspect the bounded decompressed content for secret data.

## Review and updates

A format change requires updating its repository format evidence or provider
source contract first. Add or edit a fixture only for a concrete parser behavior.
Recompute the sidecar size and SHA-256 after any byte change, list the new case,
and bump the production parser version when interpretation or shared output can
change. Fixture revisions alone do not change parser versions.

The fixture-policy tests reject unmanifested payloads, orphaned manifests,
oversized files, checksum or size drift, unknown production identities, unsafe
paths, empty case/sanitization lists, and common credential-shaped content.
