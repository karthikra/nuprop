"""Security primitives for the M16-M20 surface: token vault (Fernet-backed
encryption with fail-loud semantics) and OAuth state issuance / verification
(HMAC-signed, time-limited, single-use via Redis-backed nonce dedup)."""
