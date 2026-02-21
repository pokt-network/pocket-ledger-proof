# Pocket Ledger Proof of Ownership

A single-file web app for proving ownership of Pocket Network (POKT) addresses stored on a Ledger hardware wallet. Supports both direct Ledger USB connection and mnemonic-based recovery for when the Pocket Ledger app is unavailable.

**Live:** https://pokt-network.github.io/pocket-ledger-proof/

## How It Works

### Option A — Ledger USB (recommended)

1. Connect your Ledger via USB and open the Pocket app
2. The app retrieves your public key and derives your POKT address
3. A timestamped challenge message is blind-signed on-device
4. The Ed25519 signature is verified locally in the browser
5. Export a JSON proof file that anyone can independently verify

### Option B — Mnemonic Recovery

If you cannot install the Pocket Ledger app on your device (see [Sideloading Guide](SIDELOAD.md)), you can derive your keys from your 24-word recovery phrase directly in the browser:

1. **Disconnect from the internet** before entering your mnemonic
2. Open the page (it works offline — save the HTML file first)
3. Click "Recover with Mnemonic" at the bottom of the Generate Proof card
4. Enter your 24-word recovery phrase (and passphrase if you set one)
5. Click "Derive Key & Prove Ownership"
6. Export the proof JSON file

The mnemonic recovery uses BIP32-Ed25519 key derivation (matching the Ledger firmware's implementation) with zero external dependencies — all cryptography runs in-browser using Web Crypto API and embedded tweetnacl.

**Security notes:**
- Your mnemonic is never transmitted — all derivation happens locally
- Inputs are cleared immediately after key derivation
- Use a private/incognito window and close it after
- Mnemonic recovery works in any modern browser (not just Chrome/Edge)

## Finding Your Address

If the generated address doesn't match your known POKT address, try the following:

1. **Try different account indexes** — If you created multiple accounts, each index (0, 1, 2...) derives a different address. Start with index 0 and increment until you find a match.
2. **Try the other derivation path format** — Switch between Standard and Extended in the dropdown and re-derive. Different wallets may have used different path formats.
3. **If using mnemonic recovery** — You must re-enter your mnemonic each time you change the index or path format, as the key is derived at the moment you click "Derive Key & Prove Ownership".

### Derivation path format

The app offers two path formats:

| Format | Path | Notes |
|--------|------|-------|
| **Standard** (default) | `44'/635'/index` | Matches the Ledger app's test suite |
| **Extended** | `44'/635'/index'/0/0` | Full BIP-44 structure |

Try **Standard at index 0** first. If your address doesn't match, try **Extended at index 0**. If neither matches, increment the index. The derivation path is recorded in the exported proof JSON so verifiers know which was used.

## Requirements

### Ledger USB mode
- **Browser:** Chrome or Edge (WebHID support required)
- **Device:** Ledger Nano S, S+, or X
- **App:** [Pocket Ledger app](https://github.com/obsidiansystems/ledger-app-pocket) installed on the device — see [Sideloading Guide](SIDELOAD.md)
- **Setting:** Blind Signing must be enabled in the Pocket app settings

> **Brave users:** WebHID is disabled by default. Go to `brave://flags`, search for "WebHID", set it to **Enabled**, and relaunch.

### Mnemonic recovery mode
- **Browser:** Any modern browser (Chrome, Firefox, Safari, Edge)
- **Network:** Works fully offline

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
- **BIP-44 path:** `44'/635'/...` (variable length, see Derivation Path section)
- **Address derivation:** First 20 bytes of `SHA256(ed25519_pubkey)`

## License

MIT
