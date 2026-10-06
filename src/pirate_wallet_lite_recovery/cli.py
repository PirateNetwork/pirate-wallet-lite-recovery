"""Interactive, local-only recovery command."""

import argparse
import getpass
import os
import shlex
import sys
import warnings
from pathlib import Path

from . import __version__
from .legacy import RecoveryError, bech32, recover


def normalise_path(raw):
    """Accept a literal path, matching quotes, or a Unix shell-escaped path."""
    raw = raw.strip()
    exact = Path(raw).expanduser()
    if exact.is_file():
        return exact
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        raw = raw[1:-1]
    elif os.name != 'nt':
        try:
            words = shlex.split(raw)
            if len(words) == 1:
                raw = words[0]
        except ValueError:
            pass
    return Path(os.path.expandvars(raw)).expanduser()


def recover_file(path, password_provider, file_format='auto', legacy_android_password=False):
    """Open only the file explicitly selected by the user, in read-only mode."""
    from .skull_island import recover_binary, recover_json

    with path.open('rb') as stream:
        prefix = stream.read(4096)
        stream.seek(0)
        if file_format == 'auto':
            json_prefix = prefix.removeprefix(b'\xef\xbb\xbf').lstrip()
            if json_prefix.startswith(b'{'):
                file_format = 'skull-island-json'
            elif path.name.lower() == 'arrr-wallet.dat':
                file_format = 'skull-island-dat'
            else:
                file_format = 'lite'
        if legacy_android_password and file_format != 'skull-island-dat':
            raise RecoveryError('The legacy Android option requires --format skull-island-dat.')
        if file_format == 'skull-island-json':
            return recover_json(stream, password_provider)
        if file_format == 'skull-island-dat':
            return recover_binary(stream, password_provider,
                                  legacy_android_password=legacy_android_password)
        return recover(stream, password_provider)


def display(result):
    print('\nSeed phrase and keys')
    print('Keep this information private. Anyone with spending keys can spend the funds.')
    if result.get('seed'):
        print('\nEnglish seed phrase:\n' + result['seed'])
    if not result['complete']:
        print('\nPartial recovery')
        print(result['error'])
        print('The following records were recovered before the error. Other keys may be missing.')
    elif result.get('scope') == 'seed-only':
        print('\nSeed phrase recovered from the Skull Island JSON backup.')
    else:
        print('\nSeed and key section recovered. Transaction history has not been checked.')
    for message in result.get('warnings', []):
        print(message)
    for index, record in enumerate(result['shielded'], 1):
        label = ('Seed account ' + str(record['account']) if record['kind'] == 0 else
                 'Imported spending key' if record['kind'] == 1 else 'Viewing-only key')
        print('\nSapling key ' + str(index) + ': ' + label)
        if record.get('export'):
            print('Spending key:\n' + record['export'])
        elif record['kind'] == 0:
            print('Use the seed phrase to restore this account.')
        else:
            print('This viewing key cannot be used to spend funds.')
        if record.get('public'):
            print('Viewing key:\n' + bech32('zxviews', record['public']))
    for index, record in enumerate(result['transparent'], 1):
        label = 'Seed-derived' if record['kind'] == 0 else 'Imported'
        print('\nLegacy transparent key ' + str(index) + ': ' + label)
        if record.get('public'):
            print('Address: ' + record['public'])
        if record.get('export'):
            print('Legacy WIF:\n' + record['export'])
        else:
            print('This legacy key is restored through the seed phrase.')
        print('A legacy WIF is not a Sapling spending key.')
    if result.get('diversifiers'):
        print('\nDiversified addresses in this file: ' + str(len(result['diversifiers'])))
    if result.get('scope') == 'seed-only':
        print('\nKeep the recovered seed phrase private and keep all original backups.')
    else:
        print('\nRecord the seed account numbers and any separately imported spending keys.')
        print('The seed phrase does not restore separately imported spending keys.')
    print('Check the restored addresses and balance before removing any backups.')
    print('The input file was not changed. No recovery information was saved.')


def parser():
    command = argparse.ArgumentParser(
        prog='pirate-wallet-lite-recovery',
        description='Recover a seed phrase and keys locally from Pirate Wallet Lite or Skull Island files.',
        epilog='Requires an interactive terminal. Wallet files are read-only; passwords are entered at the prompt.')
    command.add_argument('wallet', nargs='?', help='path to a working copy of the wallet file')
    command.add_argument('--format', choices=('auto', 'lite', 'skull-island-json', 'skull-island-dat'),
                         default='auto', help='input format (default: auto)')
    command.add_argument('--version', action='version', version='Pirate Wallet Lite Recovery ' + __version__)
    command.add_argument('--self-test', action='store_true',
                         help='check the installed program using public synthetic data; no wallet files are read')
    command.add_argument('--skull-island-legacy-password', action='store_true',
                         help='recover a native file affected by the old Skull Island Android password bug; requires --format skull-island-dat')
    return command


def main(argv=None):
    args = parser().parse_args(argv)
    if args.self_test:
        if args.wallet or args.skull_island_legacy_password:
            raise RecoveryError('Do not supply a wallet file with --self-test.')
        from .self_test import run
        run()
        print('Self-test passed. No wallet files were read.')
        return 0
    if args.skull_island_legacy_password and args.format != 'skull-island-dat':
        raise RecoveryError('The legacy Android option requires --format skull-island-dat.')
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RecoveryError('Run this command in an interactive terminal. Do not redirect the output.')
    print('Pirate Wallet Lite Recovery ' + __version__)
    print('Use a working copy and keep the original file and a separate backup.')
    print('Disconnect from the internet before entering the password. Do not share this screen.')
    path = normalise_path(args.wallet or input('Wallet file path: '))
    if not path.is_file():
        raise RecoveryError('Wallet file not found.')
    confirmation = input('Type RECOVER to display the seed phrase and keys: ').strip()
    if confirmation != 'RECOVER':
        print('Cancelled. The wallet file was not changed.')
        return 1

    def read_password():
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            return getpass.getpass('Wallet password (hidden): ')

    result = recover_file(path, read_password, args.format, args.skull_island_legacy_password)
    display(result)
    return 0 if result['complete'] else 2


def entrypoint():
    code = 1
    try:
        code = main()
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled. The wallet file was not changed.')
    except RecoveryError as error:
        print('Recovery stopped: ' + str(error), file=sys.stderr)
    except getpass.GetPassWarning:
        print('Password entry could not be hidden. Use a normal terminal.', file=sys.stderr)
    except OSError:
        print('The file could not be read. The wallet file was not changed.', file=sys.stderr)
    except Exception:
        # A traceback can expose recovery state. Keep error output independent
        # of the selected file, password, and decrypted values.
        print('Recovery stopped because of an unexpected error. Keep all backups.', file=sys.stderr)
    finally:
        if getattr(sys, 'frozen', False) and os.name == 'nt' and sys.stdin.isatty():
            # Keep an Explorer-launched console visible. Command flags used by
            # CI must not pause or require any user input.
            if not any(flag in sys.argv for flag in ('--self-test', '--help', '-h', '--version')):
                try:
                    input('\nPress Enter to close this window.')
                except (KeyboardInterrupt, EOFError):
                    pass
    raise SystemExit(code)
