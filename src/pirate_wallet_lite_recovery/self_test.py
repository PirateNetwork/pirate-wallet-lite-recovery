"""Installed-package checks using public synthetic data only."""

import io
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from nacl.secret import SecretBox

from .legacy import RecoveryError, bech32, password_key, recover

# Derived independently by the Stashi native SDK from a public BIP39 vector.
_PUBLIC_SK = bytes.fromhex("0393157aa900000080b3a165be22405f626efef37aa7010e7d5083c641fbcb8bd7f1483a96e3c76442cebb2a2ec0be10a71005a950d5ef5adbc92ab3d56bf2e68eb01b3d55bfcb260d10418bca426ee819431b1283bde3d3572b8d5af32edf84ad44e1ee1fee897f08c0371dcc8e8059c5859bc1b9617718daec1ea7e8dbc23c4848d834d5e675e19f54f5ddda3e953986bfaa1ff32e70da56e258aa1ab8d0c3d4fe03270d07f23861")
_PUBLIC_XFVK = bytes.fromhex("0393157aa900000080b3a165be22405f626efef37aa7010e7d5083c641fbcb8bd7f1483a96e3c76442b14e4671cd0d3f92a4c15171853e769d2598e730bdc0a34110efe1bb0cc8d054209c08a5c0b81183acf1d7f0f1fc8a874a0d3fde182abc62ba1381e3f369bb49c0371dcc8e8059c5859bc1b9617718daec1ea7e8dbc23c4848d834d5e675e19f54f5ddda3e953986bfaa1ff32e70da56e258aa1ab8d0c3d4fe03270d07f23861")
_EXPECTED_SK = "secret-extended-key-main1qwf3274fqqqqpq9n59jmugjqta3xalhn02nszrna2zpuvs0mew9a0u2g82tw83mygt8tk23wczlppfcsqk54p400ttduj24n644l9e5wkqdn64dlevnq6yzp309yymhgr9p3ky5rhh3ax4et34d0xtklsjk5fc0wrlhgjlcgcqm3mnywspvutpvmcxukzaccmtkpaflgm0prcjzgmq6dten4ux04fawamglf2wvxh74pluewwrd9dcjc4gdt35xr6nlqxfcdqlerscgyhy3tk"
_EXPECTED_XFVK = "zxviews1qwf3274fqqqqpq9n59jmugjqta3xalhn02nszrna2zpuvs0mew9a0u2g82tw83myg2c5u3n3e5xnly4yc9ghrpf7w6wjtx88xz7upg6pzrh7rwcverg9ggyupzjupwq3swk0r4ls787g4p62p5lauxp2h33t5yupu0eknw6fcqm3mnywspvutpvmcxukzaccmtkpaflgm0prcjzgmq6dten4ux04fawamglf2wvxh74pluewwrd9dcjc4gdt35xr6nlqxfcdqlerscgtj9wct"

# Ciphertext generated independently by Skull Island's Node crypto writer.
_PUBLIC_SKULL_JSON = "{\"settings\":{\"currentCoin\":\"pirate\",\"explorerURL\":\"https://explorer.pirate.black/\",\"language\":\"English\",\"currency\":\"USD\",\"minimumBlock\":{\"pirate\":0},\"password\":\"5cca7720aff812a0661d96ad26f21a4b05f4ff49e47c2286d767fef2a3e261dea9a15551bc4b9109d54b4b6e029eaaae5834c79eb2bb58f5f2817726127a8468\",\"passPhrase\":\"48c7cc72a56f63dda09aba3fe2acca825473c1e1d020787fce4e7f77e80bc750608269cd2540529fbb42da1ded0e5333de9e7aa5d4200ab194bf444557bc2652c74fc0cab6751a90e04323beab182b1efbd4861156e3bdc7808ce961bc37e73355264ef9e15eddd414f16524c868f04da80b69c124ae4550ac642c02c80b2c41cbdd8c931dd81f2f6634bab9d6129636f7e38552d3e52ebcd4d3705249e9b75b2fb1ff8f591e5e85936f84f4a0e364d9d0efb6616c4e21b4becc179505481976\",\"saveData\":true}}".encode('ascii')


def synthetic_wallet(password='public self-test password'):
    entropy, nonce = bytes(32), bytes(range(24))
    box = SecretBox(password_key(password))
    cipher = box.encrypt(entropy, nonce).ciphertext
    imported_cipher = box.encrypt(_PUBLIC_SK, nonce).ciphertext
    # Outer wallet 24, keys 21; encrypted entropy followed by one imported key.
    header = struct.pack('<QQB', 24, 21, 1) + cipher + bytes([24]) + nonce + bytes(32)
    record = struct.pack('<BIB', 1, 1, 1) + b'\x00' + _PUBLIC_XFVK + b'\x00'
    record += b'\x01' + bytes([len(imported_cipher)]) + imported_cipher
    record += b'\x01' + bytes([24]) + nonce
    return header + b'\x01' + record + b'\x00\x00'


def run():
    result = recover(io.BytesIO(synthetic_wallet()), lambda: 'public self-test password')
    if not result['complete'] or result['seed'] != ' '.join(['abandon'] * 23 + ['art']):
        raise RecoveryError('Installed seed recovery check failed.')
    if result['shielded'][0]['export'] != _EXPECTED_SK:
        raise RecoveryError('Installed spending-key encoding check failed.')
    if bech32('zxviews', _PUBLIC_XFVK) != _EXPECTED_XFVK:
        raise RecoveryError('Installed viewing-key encoding check failed.')
    try:
        recover(io.BytesIO(synthetic_wallet()), lambda: 'wrong synthetic password')
    except RecoveryError:
        pass
    else:
        raise RecoveryError('Installed password verification check failed.')
    # Ensure the packaged cryptography backend can run AES-CBC, not merely import.
    cipher = Cipher(algorithms.AES(bytes(32)), modes.CBC(bytes(16)))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(bytes(16)) + encryptor.finalize()
    decryptor = cipher.decryptor()
    if decryptor.update(encrypted) + decryptor.finalize() != bytes(16):
        raise RecoveryError('Installed AES backend check failed.')
    from .skull_island import recover_binary, recover_json
    skull = recover_json(io.BytesIO(_PUBLIC_SKULL_JSON),
                         lambda: 'Public Skull Island password: \u00e9\u96ea!')
    if skull['seed'] != result['seed'] or skull['scope'] != 'seed-only':
        raise RecoveryError('Installed Skull Island JSON recovery check failed.')
    native = recover_binary(io.BytesIO(synthetic_wallet()), lambda: 'public self-test password')
    if not native['complete'] or native['shielded'][0]['export'] != _EXPECTED_SK:
        raise RecoveryError('Installed Skull Island native recovery check failed.')
