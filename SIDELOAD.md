# Sideloading the Pocket App onto a Ledger Device

The Pocket Ledger app is not available in Ledger Live, but you can sideload it onto your Ledger to sign Morse proof-of-ownership challenges.

> **Note:** Sideloading is safe. The Ledger secure element isolates apps — a sideloaded app cannot access your seed phrase or other apps' data.

## Supported Devices

| Device | Firmware | Status |
|--------|----------|--------|
| Nano S | 2.1.0+ | Tested and verified |
| Nano S+ | 1.1.0+ | Supported (build target available) |
| Nano X | — | Build target available, but sideloading on Nano X requires developer hardware |

## Prerequisites

- **Docker** installed and running
- **Python 3** with pip or pipx
- **USB cable** for your Ledger

## Step 1: Install ledgerctl

```bash
# Using pipx (recommended)
pipx install ledgerwallet

# Or using pip
pip3 install --user ledgerwallet
```

Verify it works:

```bash
ledgerctl --help
```

## Step 2: Set up Custom CA (one-time)

This lets your Ledger accept apps not signed by Ledger.

1. **Unplug** your Ledger
2. **Hold the RIGHT button** and plug it back in — this boots into Recovery mode
3. **Enter your PIN** on the device
4. Run:
   ```bash
   ledgerctl install-ca Dev
   ```
5. **Approve** on the device screen
6. Unplug and replug normally

## Step 3: Build and generate the app manifest

Choose your device target: `nanos`, `nanosplus`, or `nanox`.

```bash
# Set your target device
DEVICE=nanos  # or: nanosplus, nanox

git clone -b develop https://github.com/obsidiansystems/ledger-app-pocket.git
cd ledger-app-pocket
```

Build the binary (if you don't already have one):

```bash
docker run --rm -ti \
  --env APP_NAME=pocket \
  --env RUST_NANOS_SDK_GIT="https://github.com/LedgerHQ/ledger-device-rust-sdk.git" \
  --env HOST_UID=$(id -u) \
  --env HOST_GID=$(id -g) \
  -v "$(pwd):/app" \
  ghcr.io/ledgerhq/ledger-app-builder/ledger-app-builder:latest \
  docker/run-build-in-docker.sh
```

Generate the installation manifest:

```bash
cp rust-app/Cargo.toml docker-outputs/$DEVICE/
cp rust-app/*.gif docker-outputs/$DEVICE/

docker run --rm \
  -v "$(pwd):/app" \
  -w /app/docker-outputs/$DEVICE \
  ghcr.io/ledgerhq/ledger-app-builder/ledger-app-builder:latest \
  bash -c "cargo install cargo-ledger --version '=1.2.4' --force 2>&1 && \
    mkdir -p src && touch src/main.rs && \
    cargo ledger --use-prebuilt pocket --hex-next-to-json build $DEVICE"
```

This creates `app_$DEVICE.json` and `app.hex` in `docker-outputs/$DEVICE/`.

## Step 4: Free space on the device (Nano S only)

The Nano S has limited memory (320KB). You may need to remove other apps to make room:

```bash
# Check what's installed
ledgerctl list

# Remove apps to free space (can be reinstalled later from Ledger Live)
ledgerctl delete "AppName"
```

The Nano S+ has significantly more memory and typically doesn't need this step.

## Step 5: Install the Pocket app

Make sure the device is **unlocked** and on the **dashboard** (no app open).

```bash
cd docker-outputs/$DEVICE
ledgerctl install -f app_${DEVICE}.json
```

The device will show "Processing..." and then the Pocket app will appear in your app list.

## Step 6: Verify it works

1. Scroll to **Pocket** on your Ledger and open it (press both buttons)
2. You should see **"Pocket 0.1.3"** on the screen
3. Open the [Pocket Ledger Proof](https://pokt-network.github.io/pocket-ledger-proof/) web app in Chrome
4. Click **Connect**, then **Get Address**
5. Confirm on the device

## Troubleshooting

### "The requested interface implements a protected class"
You're using an older version of the web app that uses WebUSB. Use the latest version which uses WebHID.

### "No app open — please open the Pocket app on your Ledger"
Scroll to the Pocket app on your Ledger and open it before clicking Get Address.

### App freezes when opening
The app was installed with incorrect parameters. Delete it and reinstall using the Docker-generated manifest (not a hand-crafted one):
```bash
ledgerctl delete Pocket
ledgerctl install -f app_${DEVICE}.json
```

### "Invalid status 5103" during install
Not enough memory on the device. Delete other apps to free space (see Step 4).

### Brave browser doesn't show the device picker
WebHID is disabled by default in Brave. Go to `brave://flags`, search for "WebHID", enable it, and relaunch.

### ledgerctl not found after install
If you used pipx, make sure `~/.local/bin` is in your PATH. Run `pipx ensurepath` and restart your terminal.

## Uninstalling

```bash
ledgerctl delete Pocket
```

Your seed and other apps are not affected.
