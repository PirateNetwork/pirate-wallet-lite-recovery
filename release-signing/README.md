# Building and signing releases

Release packages are made on five native GitHub-hosted runners. The workflow uses
Python 3.13.16 and hash-pinned dependency wheels from `requirements-build.lock`,
which includes the runtime `requirements.lock`. PyInstaller 6.22.3 builds one
console executable with the CFFI backend and mnemonic wordlists included.

| Package target | Build/test runner | Conservative release baseline |
| --- | --- | --- |
| `windows-x64` | `windows-2022`, x64 | Windows 10/11 x64; CI uses Windows Server 2022 |
| `linux-x64` | `ubuntu-22.04`, x64 | glibc 2.35+, Ubuntu 22.04 or newer |
| `linux-arm64` | `ubuntu-22.04-arm`, ARM64 | glibc 2.35+, Ubuntu 22.04 or newer |
| `macos-x64` | `macos-15-intel`, Intel | macOS 15+ |
| `macos-arm64` | `macos-14`, Apple Silicon | macOS 14+ |

The Linux builds use the oldest selected runner to limit the glibc requirement.
Older macOS versions may work but are not promised until the compiled dependencies
and executable have been tested there. Windows Authenticode and Apple Developer
signing/notarization are not configured; PGP verifies the downloaded archive.

## Run from source

Source use requires Python **3.11 or newer**; Python 3.13.16 is the exact native
release-build version, rather than a requirement for source recovery. Download a
reviewed source release or clone the repository, open a terminal in its project
directory, and create a fresh virtual environment. Install dependencies before
taking the computer offline for recovery.

On Windows, open PowerShell in the project directory. Check that `py -3 --version`
reports Python 3.11 or newer, then run:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes --only-binary=:all: -r requirements.lock
$env:PYTHONPATH = 'src'
python -m pirate_wallet_lite_recovery --self-test
python -m pirate_wallet_lite_recovery "$env:USERPROFILE\Pirate Recovery\zero_wallet.json"
```

If PowerShell blocks virtual-environment activation, skip the activation line
and replace `python` in the remaining commands with
`.\.venv\Scripts\python.exe`; activation is convenient but not required.

On Linux or macOS, check that `python3 --version` reports Python 3.11 or newer,
then run these commands in the project directory:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes --only-binary=:all: -r requirements.lock
export PYTHONPATH=src
python -m pirate_wallet_lite_recovery --self-test
python -m pirate_wallet_lite_recovery "$HOME/Pirate Recovery/zero_wallet.json"
```

The final line in each example is for recovery: change the quoted path to the
working copy of your own backup, keeping the quotes when its path contains spaces.
Run recovery while offline. The tool asks for the backup password with hidden
input and displays recovered secrets in the terminal. Keep the original backup
safe and follow the root README's recovery and security instructions. Format
options are the same for source use and the executable, for example:

```text
python -m pirate_wallet_lite_recovery --format skull-island-dat "path/to/working-copy/arrr-wallet.dat"
```

`PYTHONPATH=src` runs the reviewed local package directly; no package-install step
is needed. Keep using the same project directory and virtual environment when
rerunning source commands. On a new terminal, reactivate the environment and set
`PYTHONPATH` again.

## Local build

Use a fresh virtual environment on the same operating system and processor as
the desired package. Python 3.13.16 is the exact CI interpreter; building with
another supported Python version produces different binaries. From the project
directory, activate the virtual environment, then run:

```text
python -m pip install --require-hashes --only-binary=:all: -r requirements-build.lock
python scripts/build_release.py --target windows-x64
```

Replace `windows-x64` with the matching target from the table. Cross-compiling is
refused. For source tests, set `PYTHONPATH` to `src` and run:

```text
python -m unittest discover -s tests -v
python -m pirate_wallet_lite_recovery --self-test
```

PowerShell sets that variable with `$env:PYTHONPATH = 'src'`; Linux and macOS use
`export PYTHONPATH=src`. The build script tests `--self-test` on the built executable
and again after extracting its archive in a separate directory without source
import paths. All tests use synthetic data. No wallet, recovery result, private
release key, virtual environment, or build directory is included in an archive.

For version 1.0.0 the archive name is
`pirate-wallet-lite-recovery-1.0.0-<target>.zip` on Windows and
`pirate-wallet-lite-recovery-1.0.0-<target>.tar.gz` elsewhere. It contains a single
directory with that basename, holding the executable, `README.md`, `SECURITY.md`,
`LICENSE`, `public_key.asc`, `BUILD-INFO.json`, `THIRD_PARTY_LICENSES/`, and this
document at `release-signing/README.md`.

Automatic prereleases keep this declared-version archive naming scheme. The
commit suffix appears in the release tag, not in the archive filenames;
`BUILD-INFO.json` records the exact source commit for each package.

The package contains license text and metadata for the pinned installed
dependencies and the bundled Python interpreter. Build metadata records the
target, interpreter, PyInstaller version, runtime dependency versions, source
commit, and successful self-test. This is traceability information; the build is
not claimed to be bit-for-bit reproducible.

## Configure the protected signing environment

Do this in the new repository before the first push to `main` that should publish
a prerelease, or before pushing a stable release tag. No private key is
stored in this repository or copied from another local project.

1. In GitHub repository **Settings → Environments**, create `release-signing`.
2. For fully automatic publication after successful `main` pushes, do not add
   required reviewers to this environment. Required reviewers may be retained if
   signing approval is desired, but every release will wait for that approval.
   If approval is enabled, use **Prevent self-review** where practical and disable
   administrator bypass of protection rules.
3. Under deployment restrictions select **Selected branches and tags**, then add
   a **Branch** rule for `main` and a **Tag** rule for `v*`. Protect `main` and
   release tags with repository rulesets, restrict who can create/update release
   tags, and require reviews for changes to workflows and signing scripts. Keep
   `main` as the repository's default branch.
4. Add these two **environment secrets**, using the same existing release-signing
   identity as Stashi:

   - `LINUX_GPG_PRIVATE_KEY_B64`: base64 of an exported, passphrase-protected signing
     private key. The imported key must have the expected primary fingerprint.
   - `LINUX_GPG_PASSPHRASE`: its passphrase, without newline characters.

If a tag ruleset restricts creation, allow the authorised GitHub Actions release
job to create new commit-suffixed tags. The publisher uses the repository's
`GITHUB_TOKEN` and never moves an existing tag. A rule that blocks that token from
creating tags will also block automatic publication.

Use the existing secure key backup and existing secret values. Do not paste them
into a terminal command, issue, chat, workflow file, or build log. Base64 is an
encoding, not encryption. Store these as environment secrets rather than broad
repository/organization secrets so build and pull-request jobs cannot receive them.
The workflow fails if either secret is missing; it never silently releases
unsigned packages. GitHub environment protections must be configured by the
repository owner; merely naming an environment in a workflow does not protect it.

Expected primary fingerprint:

```text
E4FB2399AECCF9B9447DED472CE65343401553A6
```

`public_key.asc` was copied from the existing Stashi release-signing public key.
It is safe to distribute. Confirm this fingerprint using an independently trusted
channel; importing a key from the same download alone does not establish identity.

## Release flow

### Automatic prereleases from main

Every successful push to `main` tests, builds, and tests all five native packages,
then signs the complete set and creates a public GitHub **prerelease**. Its tag is
`v<version>-<first-12-commit-characters>`, for example
`v1.0.0-a1b2c3d4e5f6`, and points to the exact event commit used to build the
packages. These are separate, immutable releases for individual commits, not a
rolling tag that is moved to newer code. Rapid pushes do not cancel an earlier
`main` release run.

The gate requires matching `project.version` and package `__version__` values and
checks that the event commit is in `main`'s history. It reads the versions from
Git blobs without executing the release source. A version bump is not needed for
each push: commits sharing version 1.0.0 receive different commit-suffixed tags.
Change both version declarations together when changing the declared version.
The generated prerelease notes identify its version and full source commit.

### Stable releases from version tags

After reviewing a release candidate, create a matching tag such as `v1.0.0` on a
reviewed commit in `main`'s history. A stable release tag must use exactly `v` plus
three numeric version components. The gate checks the tag and event SHA and
requires both version declarations to match the tag. The workflow signs the
packages and creates a **draft** stable GitHub release. Review the draft and build
results before publishing it.

Pull requests, pushes to other branches, and manual runs test and build packages
only; they do not sign or publish releases. Signing waits for the appropriate
release gate and all five successful build/test jobs. The gate loads its verifier
from the default branch, verifies that checkout against the remote default branch,
and identifies an immutable trusted commit for the signing job. The signing job
checks out the signing script and public key from that trusted commit, without
installing dependencies or executing the packaged programs after secrets are
available.

The signer requires exactly the five expected archives, checks each archive's
allowed file layout, version, target, successful self-test marker, and bundled
public key, and refuses unexpected files such as wallet backups.
Archive entries are also checked for wallet/secret names at every depth, with an
8 MiB limit per metadata/license file, at most 2,048 entries, and 512 MiB limits
for both compressed and total uncompressed archive size. GPG runs with
`--no-options` and an explicitly isolated temporary keyring. The private key is
imported through standard input, and the passphrase uses a pipe with
`--passphrase-fd 0`; neither is put on the command line or written as an exported
key/passphrase file. The signer verifies public/private fingerprints, verifies
every new signature, terminates that keyring's agent, and removes the temporary
keyring on success or failure. GPG diagnostics are not echoed into workflow logs.
The signing runner is ephemeral.

Release assets are the five archives, a detached armored `.asc` signature for
each, `SHA256SUMS`, detached `SHA256SUMS.asc`, and `public_key.asc`. The signed
checksum manifest includes the five archive hashes and the public key hash. Only
these public assets are uploaded from the signing job.

A final job with `contents: write` publishes the commit-specific prerelease for
a `main` push, or prepares the stable draft for a version-tag push. It runs only
after tests, builds, and signing succeed. The signing job has read-only repository
permissions, and build/PR jobs have no signing secrets. Existing releases and tags
are not replaced automatically; a collision requires maintainer review rather
than overwriting public assets.

## Signing tests and download verification

Run `python scripts/test_signing.py` with GPG installed. It generates a temporary
Ed25519 test key and tests successful signing/verification, tamper detection,
missing secrets, wrong fingerprint, wrong passphrase, unexpected wallet files,
wallet/secret files nested under licenses, oversized metadata, and incomplete
releases. It never opens the user's default GPG keyring and never
uses the real release signer. CI runs this test on Linux x64.
`python scripts/test_release_validation.py` separately checks release gates,
version and event mismatches, and commits outside the permitted branch history in
disposable local repositories. Fixture commits explicitly disable GPG signing.

Download verification is optional, as described at the end of the root README.
If choosing to verify a downloaded archive, do it before extraction:

```text
gpg --import public_key.asc
gpg --fingerprint E4FB2399AECCF9B9447DED472CE65343401553A6
gpg --verify SHA256SUMS.asc SHA256SUMS
gpg --verify <archive>.asc <archive>
```

Check the displayed fingerprint independently and require a valid signature for
verification to succeed. Compare the archive's SHA-256 hash against the verified
manifest. The root README has platform-specific download, optional verification,
extraction, and launch instructions.

## Verified upstream references

Runner labels and action pins were checked on 2026-10-06 against
[GitHub runner documentation](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
[checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1),
[setup-python v7.0.0](https://github.com/actions/setup-python/releases/tag/v7.0.0),
[upload-artifact v7.0.1](https://github.com/actions/upload-artifact/releases/tag/v7.0.1),
and the first-party download-artifact tag ref. The workflow pins full commit SHAs.
The exact interpreter is listed in the
[first-party Python manifest](https://github.com/actions/python-versions/blob/main/versions-manifest.json)
and [Python 3.13.16 release](https://www.python.org/downloads/release/python-31316/).
See [PyInstaller usage](https://www.pyinstaller.org/en/stable/usage.html) and
[GitHub environment configuration](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
for the packaging and environment behavior.
