# Security Policy

## Supported scope

This repository is research software and is not intended for production custody of real blockchain funds.

## Reporting

Please report:

- secret exposure;
- accidental publication of private infrastructure paths;
- unsafe regtest/mainnet isolation behavior;
- command injection, path traversal, or data-loss risks.

Do not publish secrets, cookies, tokens, RPC credentials, or wallets in issues.

## Operational warning

The prototype is designed to operate as an external layer over Bitcoin Core RPC and must remain isolated from any mainnet datadir.
