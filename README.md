# Pirate Wallet Lite Recovery

Pirate Wallet Lite Recovery reads a copy of a Pirate Wallet Lite or Skull Island backup and displays its seed phrase and supported keys. It runs offline, opens the input file for reading only, and does not save the recovered information to a file.

The displayed seed phrase and spending keys can control your funds. Keep the terminal private. Viewing keys are also private because they can reveal transaction information.

This guide covers version **1.0.0**. The native downloads include Python and the required libraries, so you do not need to install Python to use them.

## What it can recover

For supported `arrr-light-wallet.dat` files from Pirate Wallet Lite and native `arrr-wallet.dat` files from Skull Island, the program can display:

- The 24-word English seed phrase.
- The recorded Sapling seed account numbers.
- Separately imported Sapling spending keys.
- Sapling viewing keys, including viewing-only records.
- The number of recorded diversified addresses.

For supported encrypted Skull Island `zero_wallet.json` backups, it recovers the 24-word English seed phrase only. The JSON backup does not include independently imported spending keys. If you have both JSON and native DAT backups, keep both and recover the native DAT file as well.

Normal recovery of encrypted files requires the original wallet password. The program asks for it in the terminal with typing hidden and does not accept a password as a command-line argument. The explicitly selected older Android mode described below uses the historical encryption value instead.

Reading a seed and key section successfully does not prove that every wallet record is valid or that all funds have been recovered. The program does not read the blockchain, check transaction history, or check balances. Check those in Stashi Wallet after importing the recovered information.

Binary recovery reads the seed header before the key records. If the seed header cannot be read or the encrypted seed cannot be decrypted, recovery stops before separately imported keys can be recovered. A different intact backup may still contain them.

It cannot recover a forgotten password, missing private keys from a viewing-only backup, or a missing wallet file.

## Before starting

1. Close the old wallet application before copying its file.
2. Keep the original file and make a separate backup on a device you control. Work on another copy. Do not move or overwrite the original.
3. Use a trusted computer. Do not use a public, shared, or remotely controlled computer.
4. Download the recovery program, and install Stashi Wallet if needed, while you still have an internet connection.
5. Disconnect from the internet before running recovery. Stop screen sharing, recording, terminal logging, and any service that copies clipboard contents between devices.
6. Have paper or another protected offline backup ready. Do not photograph the output or put it in a cloud note, email, chat, or issue report.

The input file may be encrypted; the recovered information shown on screen is clear text. Closing the terminal does not guarantee that terminal history, memory, or operating-system records have been erased.

## Find and copy the Lite wallet file

These are the usual locations. A portable installation or a custom data-directory setting may have stored the file somewhere else.

### Windows

1. Close Pirate Wallet Lite.
2. Press **Windows + R**.
3. Enter `%APPDATA%\Pirate` and press **Enter**.
4. Find `arrr-light-wallet.dat`. If file extensions are hidden, enable **File name extensions** in File Explorer: **View > Show** on Windows 11, or the **View** tab on Windows 10.
5. Right-click the file and select **Copy**.
6. Press **Windows + R**, enter `%USERPROFILE%`, and press **Enter**.
7. Create a folder named `Pirate Recovery` in this folder. Use a local folder that is not synchronised to a cloud service.
8. Open `Pirate Recovery` and paste the copy. Leave its name as `arrr-light-wallet.dat`.

Your working copy is now at `%USERPROFILE%\Pirate Recovery\arrr-light-wallet.dat`. The commands below use this path.

### Linux

1. Close Pirate Wallet Lite.
2. Open your file manager and go to your home folder.
3. Press **Ctrl + H** to show hidden folders.
4. Open `.pirate` and find `arrr-light-wallet.dat`.
5. Copy the file.
6. Return to your home folder, create a local folder named `Pirate Recovery`, open it, and paste the copy.

The usual original path is `~/.pirate/arrr-light-wallet.dat`. Your working copy is now at `~/Pirate Recovery/arrr-light-wallet.dat`.

### macOS

1. Close Pirate Wallet Lite.
2. Open Finder.
3. Select **Go > Go to Folder**, or press **Command + Shift + G**.
4. Enter `~/Library/Application Support/Pirate` and press **Return**.
5. Find and copy `arrr-light-wallet.dat`.
6. Select **Go > Home** and create a local folder named `Pirate Recovery`.
7. Open it and paste the copy.

Your working copy is now at `~/Pirate Recovery/arrr-light-wallet.dat`.

### If you cannot find the file

Search the computer and your own backup drives for `arrr-light-wallet.dat`. If you followed the old wallet reset instructions, also look for `arrr-light-wallet-old.dat`. Search old user profiles as well as the current one. Keep each candidate as a separate copy; do not combine files or replace one with another. You can recover a renamed backup by entering its actual filename instead of `arrr-light-wallet.dat` in the recovery command.

For an Android wallet, use an existing backup or an export provided by the original application. This program runs on a desktop computer. Keep the phone, application, and original backup intact. Do not uninstall the application, clear its storage, root the phone, or upload its files to a recovery website.

## Find and copy a Skull Island backup

Skull Island has two different files that may be useful:

- `zero_wallet.json` stores the encrypted seed phrase in application settings. It can recover the seed phrase, but not independently imported keys.
- `arrr-wallet.dat` is the native Pirate wallet file. Its supported seed and key records use the same binary format as Pirate Wallet Lite.

The verified Android source stores these files in the application's private data directories. They are not ordinary files in Android's Downloads folder and may not be accessible through the phone's file manager. Use an existing backup or a backup method already provided by the original application.

1. Look for an existing backup or export that you already saved from Skull Island. Search your own computer and backup drives for `zero_wallet.json` and `arrr-wallet.dat`.
2. Keep the original phone, application, and all existing backups intact. Do not uninstall Skull Island or clear its application data while looking for a backup.
3. Close Skull Island before making a new copy through any backup method that the original application already provides.
4. Copy the backup to the local `Pirate Recovery` folder created above. Keep its original filename. If you have both files, copy both separately.
5. Follow the download and extraction steps for your computer below.
6. Use one of the commands in [Run recovery for a Skull Island backup](#run-recovery-for-a-skull-island-backup), rather than the Lite filename in the main examples.

If you have no file backup, keep the device intact and seek help through an established PirateNetwork channel about the original application's available backup methods. Do not give anyone the password, wallet file, seed phrase, or remote access to the device.

## Download the correct release

Open the [Pirate Wallet Lite Recovery releases](https://github.com/PirateNetwork/pirate-wallet-lite-recovery/releases) and select `v1.0.0`. Download the archive for your computer and save it in your **Downloads** folder. Check that your browser has not added a suffix such as `(1)` to the filename.

Signature and checksum verification is optional. If you want to verify the download before running it, follow [Optional download verification](#optional-download-verification) at the end of this guide.

| Computer | Archive | Release baseline |
|---|---|---|
| Windows, Intel or AMD 64-bit | `pirate-wallet-lite-recovery-1.0.0-windows-x64.zip` | Windows 10 or 11, 64-bit |
| Linux, Intel or AMD 64-bit | `pirate-wallet-lite-recovery-1.0.0-linux-x64.tar.gz` | glibc 2.35 or newer; built on Ubuntu 22.04 |
| Linux, ARM64 | `pirate-wallet-lite-recovery-1.0.0-linux-arm64.tar.gz` | glibc 2.35 or newer; built on Ubuntu 22.04 |
| macOS, Intel | `pirate-wallet-lite-recovery-1.0.0-macos-x64.tar.gz` | macOS 15 or newer |
| macOS, Apple Silicon | `pirate-wallet-lite-recovery-1.0.0-macos-arm64.tar.gz` | macOS 14 or newer |

## Run on Windows

1. Open the Start menu, type **PowerShell**, and open it.
2. Go to Downloads, extract the ZIP, and enter the extracted folder. Enter these commands one at a time:

```powershell
Set-Location -LiteralPath "$env:USERPROFILE\Downloads"
Expand-Archive -LiteralPath ".\pirate-wallet-lite-recovery-1.0.0-windows-x64.zip" -DestinationPath "."
Set-Location -LiteralPath ".\pirate-wallet-lite-recovery-1.0.0-windows-x64"
```

3. Disconnect from the internet and complete the privacy steps in [Before starting](#before-starting).
4. Start recovery with your working copy:

```powershell
.\pirate-wallet-lite-recovery.exe "$env:USERPROFILE\Pirate Recovery\arrr-light-wallet.dat"
```

Keep the quotes around the wallet path. If your copy is somewhere else, replace the quoted path with its full path. You can also run `.\pirate-wallet-lite-recovery.exe` without a path and enter the path when asked.

For Skull Island, use [Run recovery for a Skull Island backup](#run-recovery-for-a-skull-island-backup). Otherwise, continue with [Read the recovery output](#read-the-recovery-output).

## Run on Linux

1. Open **Terminal**.
2. Go to Downloads and select the archive. For Intel or AMD x64:

```sh
cd "$HOME/Downloads"
archive="pirate-wallet-lite-recovery-1.0.0-linux-x64.tar.gz"
```

For ARM64, use this archive assignment instead:

```sh
archive="pirate-wallet-lite-recovery-1.0.0-linux-arm64.tar.gz"
```

3. Extract the archive and enter the folder:

```sh
tar -xzf "$archive"
cd "${archive%.tar.gz}"
```

4. Disconnect from the internet and complete the privacy steps in [Before starting](#before-starting).
5. Start recovery with your working copy:

```sh
./pirate-wallet-lite-recovery "$HOME/Pirate Recovery/arrr-light-wallet.dat"
```

Keep the quotes around the wallet path. Replace the path if your copy is somewhere else. You can also run `./pirate-wallet-lite-recovery` without a path and enter the full path when asked.

For Skull Island, use [Run recovery for a Skull Island backup](#run-recovery-for-a-skull-island-backup). Otherwise, continue with [Read the recovery output](#read-the-recovery-output).

## Run on macOS

1. Open **Applications > Utilities > Terminal**.
2. Go to Downloads and select the archive. For Apple Silicon:

```sh
cd "$HOME/Downloads"
archive="pirate-wallet-lite-recovery-1.0.0-macos-arm64.tar.gz"
```

For an Intel Mac, use this archive assignment instead:

```sh
archive="pirate-wallet-lite-recovery-1.0.0-macos-x64.tar.gz"
```

3. Extract the archive and enter the folder:

```sh
tar -xzf "$archive"
cd "${archive%.tar.gz}"
```

4. Disconnect from the internet and complete the privacy steps in [Before starting](#before-starting).
5. Start recovery with your working copy:

```sh
./pirate-wallet-lite-recovery "$HOME/Pirate Recovery/arrr-light-wallet.dat"
```

Keep the quotes around the wallet path. Replace the path if your copy is somewhere else. You can also run `./pirate-wallet-lite-recovery` without a path and enter the full path when asked.

If macOS blocks the program, see [Apple's instructions for opening an application from an unidentified developer](https://support.apple.com/102445).

For Skull Island, use [Run recovery for a Skull Island backup](#run-recovery-for-a-skull-island-backup). Otherwise, continue with [Read the recovery output](#read-the-recovery-output).

## Run recovery for a Skull Island backup

Complete the extraction steps for your operating system first. Stay in the extracted program folder, disconnect from the internet, and stop screen sharing and recording.

For `zero_wallet.json`, use the command for your operating system:

Windows PowerShell:

```powershell
.\pirate-wallet-lite-recovery.exe "$env:USERPROFILE\Pirate Recovery\zero_wallet.json"
```

Linux or macOS Terminal:

```sh
./pirate-wallet-lite-recovery "$HOME/Pirate Recovery/zero_wallet.json"
```

For the native `arrr-wallet.dat`, use:

Windows PowerShell:

```powershell
.\pirate-wallet-lite-recovery.exe "$env:USERPROFILE\Pirate Recovery\arrr-wallet.dat"
```

Linux or macOS Terminal:

```sh
./pirate-wallet-lite-recovery "$HOME/Pirate Recovery/arrr-wallet.dat"
```

Replace the quoted path if your copy is somewhere else. JSON is recognised from its contents. A native file named `arrr-wallet.dat` is labelled as Skull Island; other native files use the same Lite binary reader. You do not need to rename a backup to read its supported binary records.

Skull Island JSON uses unauthenticated AES-CBC encryption. A valid recovered mnemonic checksum does not prove that encrypted data was never modified. Verify the resulting wallet addresses and history in Stashi. A successful JSON recovery means that the seed was recovered; it does not mean that the native wallet's separate keys were recovered.

### Older Android Skull Island encryption error

Try the original wallet password first. Some Android Skull Island versions before 2.2.0 passed the literal text `[]` to native encryption instead of the password entered in the application. The [historical JavaScript call](https://github.com/PirateNetwork/cordova-plugin-litewallet/blob/9bf9264e77b11926cf54160d1d07f8061d841b2b/www/litewallet.js#L89) and [Skull Island's migration code](https://github.com/PirateNetwork/Skull-Island/blob/e3e54163ba61205dd63d39a8c4dbbea41302647c/SaplingMobile/src/App.jsx#L294) document this error.

If a native `arrr-wallet.dat` came from that older Android application and the ordinary password fails, you can explicitly select the historical mode. It uses that one known value and does not search for passwords.

Windows PowerShell:

```powershell
.\pirate-wallet-lite-recovery.exe --format skull-island-dat --skull-island-legacy-password "$env:USERPROFILE\Pirate Recovery\arrr-wallet.dat"
```

Linux or macOS Terminal:

```sh
./pirate-wallet-lite-recovery --format skull-island-dat --skull-island-legacy-password "$HOME/Pirate Recovery/arrr-wallet.dat"
```

This mode applies only to the old native DAT file, not `zero_wallet.json` or ordinary Lite files. It is never tried automatically. Check the resulting wallet addresses before relying on the result, and keep all original backups if it fails.

## Read the recovery output

1. Check that no one else can see or record the terminal.
2. If no path was supplied on the command line, the program asks `Wallet file path:`. Enter the full path to the working copy. A command-line path needs quotes when it contains spaces.
3. At `Type RECOVER to display the seed phrase and keys:`, enter `RECOVER` in capital letters and press **Enter**. Any other answer cancels recovery.
4. In normal recovery, if the file is encrypted, enter its original password at `Wallet password (hidden):` and press **Enter**. No characters are displayed while you type. This is normal. The explicitly selected older Android mode uses the historical value instead of showing this prompt.
5. Read the result. Write down the displayed seed words in their exact order and each separately imported spending key that you need. Keep viewing keys private as well.
6. Look for a partial recovery warning before relying on the result. A displayed seed does not mean that independently imported keys were recovered.
7. Keep every original wallet file and backup until you have checked the expected addresses, balances, and transaction history in Stashi Wallet.

The program requires an interactive terminal for both input and output. Do not add `>`, `|`, `tee`, or a terminal logging command to the recovery command. There is no automatic output file. A terminal's own scrollback can still contain the clear text output.

The Windows download waits at `Press Enter to close this window.` Read and record what you need before pressing **Enter**. An existing PowerShell window may remain open afterwards, with the output still in its scrollback.

For a recovery run, exit status 0 means the supported records in the selected file were recovered, including seed-only JSON recovery. Exit status 2 means partial binary recovery. Exit status 1 means cancellation or failure. Invalid command-line arguments also return status 2, with a usage error instead of recovery output. These statuses do not prove that all funds have been restored.

## Import the recovered information into Stashi Wallet

Install Stashi Wallet from the [official releases](https://github.com/PirateNetwork/Pirate-Unified-Light-Wallet/releases) and verify its release files using the [Stashi Wallet user guide](https://piratenetwork.github.io/Stashi-Wallet/). Recovery and importing are separate steps. Stashi needs a network connection to scan the blockchain; the recovery program does not.

### Restore the seed phrase

Follow these steps only if the program displayed a seed phrase. If recovery stopped before displaying one, keep the backup and resolve that error first.

1. Open Stashi Wallet and select **Get started > Import existing wallet**.
2. Select **English** for a seed recovered by this program.
3. Enter all 24 words in order.
4. Create the local Stashi passphrase. It is a new device password and does not have to match the old Lite password.
5. Name the wallet.
6. Enter a wallet birthday height from before the first expected transaction. If you do not know the height, select **Exact block height** and enter **1** in **Block height**. This starts scanning from block 1 and may take longer.
7. Finish setup, reconnect as needed, and keep Stashi open until the historical scan finishes.
8. Check the balance and **Activity** page.

### Recover higher seed accounts

Seed account 0 is the usual first account. In the Stashi version documented by the current migration guide, seed recovery also checks legacy Sapling accounts 1 through 5. A recovery result listing account 6 or higher requires extending the account search.

1. Open **Settings > Keys & addresses** in the restored wallet.
2. Find **Seed accounts** and read the **Next seed account** number.
3. Select **Add next account** to add the next consecutive account, or **Add 5 accounts** to add five consecutive accounts.
4. Confirm the range and wait for its scan to finish.
5. Repeat until the account numbers reported by the recovery program are covered, then check their balances and activity.

An account number is not an address number. Creating more diversified receiving addresses does not restore a higher seed account. See [Stashi's migration guide](https://piratenetwork.github.io/Stashi-Wallet/migration/).

### Import separate Sapling spending keys

A seed phrase cannot recreate a spending key that was imported separately into the old wallet. For every **Imported spending key** record:

1. Open **Settings > Keys & addresses** in Stashi.
2. Select **Spending Key** under Import keys.
3. Enter the complete Sapling spending key beginning with `secret-extended-key-main1`.
4. Enter a birthday height from before that key first received funds. If you do not know it, enter **1**.
5. Confirm the import and allow the automatic rescan to finish.
6. Open the imported key's details and compare its addresses, balance, and activity with your old records.

Use the key's details when comparing addresses. The main **Receive** screen may have a different key selected. Adding seed accounts does not restore an independently imported key.

### Viewing-only records

A Sapling viewing key begins with `zxviews1`. It can reveal supported activity within its key scope, but it cannot spend funds.

To monitor it in Stashi, select **View only** during setup, enter a wallet name, put the key in the **Sapling** viewing-key field, and choose a birthday height before its first transaction. You can also use **Settings > Keys & addresses > Viewing Key**. Wait for the scan to finish.

If the old file only contains a viewing key, this program cannot turn it into a spending key. Find the original seed phrase, spending-key backup, or wallet that holds spending authority.

### Check the result before finishing

Wait for scanning to reach the current chain height. Check every seed account and imported key that you expect to hold funds. Compare the expected balance, important transactions, and recorded receiving addresses. A missing balance may require an earlier birthday height, another seed account, a separately imported key, or a completed rescan.

Keep the original wallet and backups after migration. Do not delete them because the recovery program printed a seed phrase or Stashi accepted an import.

## Errors and partial recovery

| Result | Meaning and next step |
|---|---|
| Wallet file not found | Check the full path and quotes. Use the copy you made, not a shortcut to it. |
| Incorrect password or damaged encrypted data | Check the original wallet password locally. This result cannot distinguish a wrong password from damaged ciphertext. Try another original backup if available. |
| Unsupported file or version | Keep the file intact. Check that it came from a supported wallet. Do not rename a different wallet format or edit its bytes. |
| Truncated or damaged records | Try another untouched backup. Do not discard a backup because this copy is damaged. |
| Partial recovery | A later record failed. The program displays the seed and any valid earlier key records, but additional keys may be missing. Keep all originals and check another backup. |
| Interactive terminal required | Open PowerShell or Terminal directly. Do not run with input/output redirection or from a logging system. |
| Native program does not start | Check the operating system, processor, and release baseline. Use the correct archive or the documented source installation on a supported Python environment. |

When reporting a problem, give the operating system, release version, original wallet application, and the non-secret error message. Do not include the wallet, password, seed phrase, spending key, viewing key, terminal screenshot, or process dump. See [SECURITY.md](SECURITY.md).

## Source and release preparation

The source can be reviewed without running the program. Source use requires Python 3.11 or newer. Native builds use the Python version pinned by the release workflow. Follow the [source and release instructions](release-signing/README.md) for source installation, native builds, the signing key, GitHub environment secrets, and publishing checks. Users do not need a private PGP key to verify downloads.

## Optional download verification

These steps are optional. They check that the archive was signed by the expected PirateNetwork key and that its checksum matches. If you choose to verify it, do so before running recovery.

Download these four additional files from the same release and save them beside your archive in **Downloads**:

- The archive's `.asc` signature
- `SHA256SUMS`
- `SHA256SUMS.asc`
- `public_key.asc`

Check that your browser has not added a suffix such as `(1)` to a filename.

### Verify on Windows

1. Install GnuPG using the [official Gpg4win download](https://gpg4win.org/get-gpg4win.html). Keep the GnuPG component selected in the installer.
2. Open the Start menu, type **PowerShell**, and open it normally. Administrator access is not needed for recovery.
3. Enter the commands below one at a time. Press **Enter** after each command. If `gpg` is not recognised, close and reopen PowerShell after installation before continuing.

```powershell
Set-Location -LiteralPath "$env:USERPROFILE\Downloads"
$archive = "pirate-wallet-lite-recovery-1.0.0-windows-x64.zip"
gpg --show-keys --with-fingerprint ".\public_key.asc"
```

4. Compare the full primary-key fingerprint with the value in [Check the verification result](#check-the-verification-result). Stop if it differs.
5. Import the public key and verify both signatures:

```powershell
gpg --import ".\public_key.asc"
gpg --fingerprint E4FB2399AECCF9B9447DED472CE65343401553A6
gpg --verify "$archive.asc" "$archive"
gpg --verify ".\SHA256SUMS.asc" ".\SHA256SUMS"
```

6. Read [Check the verification result](#check-the-verification-result) before continuing. Both signatures must be valid and belong to the expected key.
7. Calculate the archive's checksum and display the expected checksums:

```powershell
(Get-FileHash -LiteralPath ".\$archive" -Algorithm SHA256).Hash
Get-Content -LiteralPath ".\SHA256SUMS"
```

8. Find the line ending in your exact archive name in `SHA256SUMS`. Compare its 64-character checksum with the checksum printed by PowerShell. Letter case does not matter. Stop if they differ.

### Verify on Linux

1. Open **Terminal** from your application menu.
2. If GnuPG is not installed, install it with your distribution's package manager. On Ubuntu or Debian:

```sh
sudo apt update
sudo apt install gnupg
```

3. Go to Downloads and choose the archive name for your computer. For Intel or AMD x64:

```sh
cd "$HOME/Downloads"
archive="pirate-wallet-lite-recovery-1.0.0-linux-x64.tar.gz"
```

For ARM64, use this archive assignment instead:

```sh
archive="pirate-wallet-lite-recovery-1.0.0-linux-arm64.tar.gz"
```

4. Display the public key's fingerprint:

```sh
gpg --show-keys --with-fingerprint "public_key.asc"
```

5. Compare the full primary-key fingerprint with [Check the verification result](#check-the-verification-result). Stop if it differs.
6. Import the public key and verify both signatures:

```sh
gpg --import "public_key.asc"
gpg --fingerprint E4FB2399AECCF9B9447DED472CE65343401553A6
gpg --verify "$archive.asc" "$archive"
gpg --verify "SHA256SUMS.asc" "SHA256SUMS"
```

7. Read [Check the verification result](#check-the-verification-result). Both signatures must be valid and belong to the expected key.
8. Check the downloaded archive against the signed checksum list:

```sh
sha256sum --check --ignore-missing "SHA256SUMS"
```

The line for your exact archive must say `OK`. Missing archives for other operating systems are expected. Stop if your archive is absent from the result or says `FAILED`.

### Verify on macOS

1. Install a macOS version of GnuPG from the [GnuPG download page](https://gnupg.org/download/index.html), which links to [GPG Suite](https://gpgtools.org/). The command-line component is MacGPG. You do not need a mail extension or a mail subscription for these commands.
2. Open **Applications > Utilities > Terminal**.
3. Go to Downloads. For Apple Silicon:

```sh
cd "$HOME/Downloads"
archive="pirate-wallet-lite-recovery-1.0.0-macos-arm64.tar.gz"
```

For an Intel Mac, use this archive assignment instead:

```sh
archive="pirate-wallet-lite-recovery-1.0.0-macos-x64.tar.gz"
```

4. Display the public key's fingerprint:

```sh
gpg --show-keys --with-fingerprint "public_key.asc"
```

5. Compare the full primary-key fingerprint with [Check the verification result](#check-the-verification-result). Stop if it differs.
6. Import the public key and verify both signatures:

```sh
gpg --import "public_key.asc"
gpg --fingerprint E4FB2399AECCF9B9447DED472CE65343401553A6
gpg --verify "$archive.asc" "$archive"
gpg --verify "SHA256SUMS.asc" "SHA256SUMS"
```

7. Read [Check the verification result](#check-the-verification-result). Both signatures must be valid and belong to the expected key.
8. Calculate the archive's checksum and display the signed checksum list:

```sh
shasum -a 256 "$archive"
cat "SHA256SUMS"
```

9. Find the line ending in your exact archive name in `SHA256SUMS`. Its 64-character checksum must match the checksum printed by `shasum`. Stop if they differ.

### Check the verification result

The expected primary-key fingerprint is:

```text
E4FB 2399 AECC F9B9 447D ED47 2CE6 5343 4015 53A6
```

Without spaces: `E4FB2399AECCF9B9447DED472CE65343401553A6`.

Compare the entire fingerprint, rather than just the final key ID or the signer's name. Confirm it through a PirateNetwork source you already trust; a public key downloaded beside an archive does not establish who owns that key by itself.

Both verification commands must report **Good signature** from the expected key. A signing subkey may have a different fingerprint; its primary key must be the fingerprint above. GnuPG may warn that the key is not certified with a trusted signature. That trust warning is different from a bad signature and does not replace checking the full fingerprint. See the [GnuPG verification documentation](https://www.gnupg.org/documentation/manuals/gnupg/GPG-Examples.html).

Stop if verification reports a bad signature, an unexpected signer, a missing public key, a revoked key, an expired key, or an expired signature. Check the release notes and obtain the correct files through the official release page before proceeding.

A PGP signature proves that the holder of the signing key signed those bytes. It does not prove that the software has no defects. PGP signing is separate from Windows Authenticode and Apple signing or notarisation. Windows or macOS may still display a warning for a PGP-verified download.
