# Security Policy

## Supported use

`zoom-sdk-python` is intended to validate Zoom API responses and webhook payload
shapes. The Python import package is `zoom_sdk`.
It is not a complete security framework for Zoom integrations.

In particular:

- it does not currently verify webhook signatures for you
- it does not manage secret rotation
- it does not attempt to sandbox or redact arbitrary user payloads beyond the
  structured logging rules already built into the client

## Reporting a vulnerability

If you discover a security issue, please report it privately to the maintainer
before opening a public issue.

Include:

- a clear description of the problem
- affected versions or commit ids
- reproduction steps when possible
- impact assessment

Please avoid publishing exploit details publicly until the issue has been
reviewed and a remediation path is available.
