# Pocket Ledger Proof of Ownership

A single-file web app for proving ownership of Pocket Network (POKT) addresses stored on a Ledger hardware wallet. Uses WebUSB to communicate directly with the Pocket Ledger app — no backend, no extensions, no installs.

**Live:** https://pokt-network.github.io/pocket-ledger-proof/

## How It Works

1. Connect your Ledger via USB and open the Pocket app
2. The app retrieves your public key and derives your POKT address
3. A timestamped challenge message is blind-signed on-device
4. The Ed25519 signature is verified locally in the browser
5. Export a JSON proof file that anyone can independently verify

The proof JSON contains the address, public key, challenge message, and signature — everything needed for offline verification.

## Requirements

- **Browser:** Chrome or Edge (WebUSB support required)
- **Device:** Ledger Nano S, S+, or X
- **App:** [Pocket Ledger app](https://github.com/aspect-build/ledger-app-pocket) installed on the device
- **Setting:** Blind Signing must be enabled in the Pocket app settings

## Verification

The app includes a built-in verifier. Upload or paste any proof JSON to check:

- Address matches the public key (SHA256 derivation)
- Ed25519 signature is valid
- Challenge format is correct
- Timestamp is recent

Verification is fully client-side — no data leaves your browser.

## Development / Testing

For testing without a physical Ledger, the app supports the [Speculos](https://github.com/LedgerHQ/speculos) emulator.

### Setup

```bash
# 1. Start Speculos with the Pocket app ELF
docker run --rm -d --name speculos-pocket \
  -v /path/to/docker-outputs/nanos:/app \
  -p 5005:5000 --platform linux/amd64 \
  ghcr.io/ledgerhq/speculos:0.9.7 \
  --model nanos /app/pocket --display headless --api-port 5000

# 2. Start the proxy server (adds CORS headers)
python3 serve.py

# 3. Open in browser
open http://localhost:8080/index.html?dev=true
```

Select "Speculos" mode in the dev panel to use the emulator with on-screen button controls.

### Automated Test

`test_speculos.py` runs the full flow (GetVersion, GetPubkey, BlindSign) against Speculos with no external dependencies beyond Python stdlib.

```bash
python3 test_speculos.py
```

## Protocol

Communicates with the Pocket Ledger app using the Alamgu blocks protocol over APDU:

- **GetPubkey (INS 0x02):** Retrieves Ed25519 public key silently
- **BlindSign (INS 0x04):** Signs arbitrary JSON with on-device approval
- **BIP-44 path:** `44'/635'/index'/0/0`
- **Address derivation:** First 20 bytes of `SHA256(ed25519_pubkey)`

## License

MIT
