# Security

Pirate Wallet Lite Recovery handles information that can control funds or reveal private transaction history. Use a trusted computer, an untouched original backup, and a separate working copy. The recovery process is offline and reads the selected input file without saving changes to it.

## Secret handling

- The seed phrase, spending keys, and viewing keys are displayed in clear text after the user confirms recovery.
- An encrypted input file does not make the displayed output encrypted.
- Passwords are entered through a hidden terminal prompt. Password text is not accepted on the command line, and there is no automatic recovery-output file.
- Recovery requires interactive terminal input and output. Output redirection and piping are rejected.
- The program does not send wallet data over a network, scan the blockchain, create transactions, or sign transactions.

The program's read-only handling does not protect against malware, screen recording, terminal logging, remote access, memory inspection, swap, crash dumps, or synchronised clipboards. Python does not provide reliable secret-memory erasure. Closing the program or clearing the screen is not a guarantee that secret data has been removed from the computer.

Do not send wallet files, passwords, seed phrases, spending keys, viewing keys, screenshots of recovery output, or memory dumps to maintainers or anyone else. Make protected offline backups and keep the original wallet until the expected funds and history have been checked in a destination wallet.

## Recovery limits

The program reads documented seed and key records from supported old wallet formats. It applies bounds, length checks, record checks, and the available checks for encrypted data. These checks have limits:

- An unencrypted file may contain damaged or altered seed bytes that still encode as a valid mnemonic. A syntactically valid seed phrase does not prove it belongs to the expected wallet.
- A seed phrase does not reproduce spending keys imported independently into the wallet.
- A viewing-only file cannot provide spending authority that it never contained.
- A partial recovery retains the recovered seed and valid earlier key records when a later record fails. Additional keys may be missing.
- Binary recovery requires a readable seed header and, for an encrypted file, a successfully decrypted seed. It cannot skip a damaged seed header to recover independently imported keys from later records.
- Skull Island JSON contains a seed only, so successfully reading it does not recover the native wallet's independently imported keys. Its AES-CBC encryption is not authenticated; password checks and a mnemonic checksum do not establish that the ciphertext was not altered.
- Key export checks are not complete elliptic-curve validation or proof that all spending and viewing keys correspond. The destination wallet must validate imported keys.
- Reading the seed and key section does not validate the remaining wallet file, blockchain history, balances, or ownership of expected addresses.
- Successful import is not proof of complete recovery. Check account coverage, birthday height, addresses, balance, and history after scanning.

Unknown formats and versions are rejected. Renaming or editing an unsupported file does not make it supported. There is no password cracking or brute-force recovery feature.

An explicitly selected mode for native Skull Island files can use the literal `[]` encryption value caused by a documented Android error before version 2.2.0. It requires `--format skull-island-dat` and `--skull-island-legacy-password`. It is never attempted automatically, does not accept a password from the command line, and is not a password-search feature.

Skull Island's supported encrypted JSON layouts are recognised explicitly. The program does not search arbitrary JSON properties for possible secrets. Android application-private storage is outside this program's scope: it reads an already available backup and does not extract data from a phone.

Tests and source review are not an independent security audit. This project makes no claim that recovery is guaranteed or that every damaged wallet can be read.

## Release verification

Download native archives from the [official repository releases](https://github.com/PirateNetwork/pirate-wallet-lite-recovery/releases). The [optional download verification steps](README.md#optional-download-verification) explain how to check the detached PGP signatures and checksum before running the program.

Expected PGP primary-key fingerprint:

```text
E4FB 2399 AECC F9B9 447D ED47 2CE6 5343 4015 53A6
```

Confirm the entire fingerprint through a PirateNetwork source you already trust. A key bundled beside the file is not an independent identity check. A valid signature ties the release bytes to the signing key; it does not establish that the program is defect-free.

PGP signatures are separate from Windows Authenticode and Apple signing or notarisation.

Only release maintainers need signing-key material. Follow the [release-signing instructions](release-signing/README.md) to configure the release environment. Keep the private key and its passphrase in the documented GitHub environment secrets, never in source control, release assets, issues, build output, or chat messages.

## Reporting a security problem

Use [GitHub private vulnerability reporting](https://github.com/PirateNetwork/pirate-wallet-lite-recovery/security/advisories/new) if the repository has it enabled. If that option is unavailable, contact a PirateNetwork maintainer through an established private channel and ask how to send a report. Do not post an exploitable security issue or confidential recovery information publicly.

Include the affected release or source commit, operating system, a description of the problem, and reproduction steps using invented test data. State whether the issue affects secret disclosure, wallet parsing, release verification, or another part of the program. A synthetic fixture is suitable; a real wallet backup is not.

For an ordinary recovery error, a public issue can contain the version, original wallet application, operating system, and the exact non-secret diagnostic. Remove private paths, usernames, addresses, and any recovered information. Maintainers should reproduce issues with synthetic data and must not ask users to share their secrets.
