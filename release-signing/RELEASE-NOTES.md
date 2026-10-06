Offline recovery of Pirate Wallet Lite and Skull Island backup files. Choose the archive for your
operating system and processor and extract it before
running the recovery tool. Read the included README and SECURITY documents first.
Optional signature and checksum verification instructions are at the end of the
README.

Supported inputs include Pirate Wallet Lite `arrr-light-wallet.dat`, Skull
Island native `arrr-wallet.dat`, and supported encrypted `zero_wallet.json`
backups. JSON recovery contains the seed phrase only; separately imported keys
require the native DAT file. The tool reads a working copy without changing it.

Release signing fingerprint:

`E4FB2399AECCF9B9447DED472CE65343401553A6`

Each archive has a detached `.asc` signature. `SHA256SUMS.asc` is a detached
signature for `SHA256SUMS`. If choosing to verify the download, verify that
signature before comparing download hashes. The public key is included in each
archive and attached separately as `public_key.asc`.

Packages: Windows x64, Linux x64/ARM64 (glibc 2.35+), macOS Intel (15+) and macOS
ARM64 (14+). The executable includes Python. Source and packaged self-tests use
only synthetic fixtures. These packages use PGP release signatures; Windows
Authenticode and Apple Developer notarization are not configured.

Successful pushes to `main` create public prereleases with immutable tags in the
form `v<version>-<first-12-commit-characters>`. Each prerelease contains packages
from that exact source commit, after all five targets pass tests and signing.
The declared package version does not need to change for every commit; archive
filenames retain that version and `BUILD-INFO.json` records the source commit.

Stable version tags such as `v1.0.0` create drafts for maintainer review. Before
publishing a stable draft, review its source changes and all five build results,
and check the six detached signatures and signed checksums. Automatic
commit-specific prereleases are not stable-release approvals.
