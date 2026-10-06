Offline recovery of Pirate Wallet Lite and Skull Island backup files. Choose the archive for your
operating system and processor, verify its PGP signature, and extract it before
running the recovery tool. Read the included README and SECURITY documents first.

Supported inputs include Pirate Wallet Lite `arrr-light-wallet.dat`, Skull
Island native `arrr-wallet.dat`, and supported encrypted `zero_wallet.json`
backups. JSON recovery contains the seed phrase only; separately imported keys
require the native DAT file. The tool reads a working copy without changing it.

Release signing fingerprint:

`E4FB2399AECCF9B9447DED472CE65343401553A6`

Each archive has a detached `.asc` signature. `SHA256SUMS.asc` is a detached
signature for `SHA256SUMS`; verify it before comparing download hashes. The public
key is included in each archive and attached separately as `public_key.asc`.

Packages: Windows x64, Linux x64/ARM64 (glibc 2.35+), macOS Intel (15+) and macOS
ARM64 (14+). The executable includes Python. Source and packaged self-tests use
only synthetic fixtures. These packages use PGP release signatures; Windows
Authenticode and Apple Developer notarization are not configured.

Maintainer review before publishing: check all five build results, verify the
six detached signatures and signed checksums, and review the source changes for
the release tag. This release was deliberately created as a draft.
