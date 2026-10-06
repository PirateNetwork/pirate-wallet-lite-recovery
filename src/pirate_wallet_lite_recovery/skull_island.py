"""Read the two source-verified Skull Island backup formats, entirely offline.

Skull Island c780b5f60ff8284b1d591631fab54dcfe97fd052 stores an encrypted
mnemonic in settings.passPhrase in zero_wallet.json. Its 1.0.3 writer
(c22833acd41cc08448a092def5474e11316ca3df, src/index.js) instead writes
top-level secretPhrase. Both use src/utils/hash.js's HMAC-SHA512/AES-CBC.

The current Cordova submodule e7c2412fa89a89a71a9e90b3ab007a56814b755d
pins piratewallet-light-cli 9cc504db0f77406b13ad55c1df3b3cb4cb00cb36. The
four key serialization files are identical to the Lite parser's pinned source.
Android LiteWalletJni.walletSave writes the raw native bytes as arrr-wallet.dat;
its Base64 transport is decoded before the file is written.
"""

import hashlib
import hmac
import json
import re

from mnemonic import Mnemonic

from . import legacy
from .legacy import RecoveryError


# These are UTF-8/ASCII HMAC keys, not hex-decoded salts. This distinction is
# required by Node's crypto.createHmac('sha512', salt) in the upstream writer.
PW_SALT = b'b442d703357362b59017c9ea8823f6b8412bad33f1a6d8fec5e41a47689fd524'
KEY_SALT = b'7b792df82bc433faa6913e3034d103f00c64360f081c7a88a8c8527652693dff'
MAX_JSON_BYTES = 1024 * 1024
MAX_CIPHERTEXT_BYTES = 4096
PASSWORD_ERROR = 'Password is incorrect or the Skull Island backup is damaged.'
JSON_WARNINGS = [
    'This JSON backup contains a seed phrase only; independently imported '
    'spending keys are not included. Use arrr-wallet.dat if available.',
    'Skull Island JSON uses unauthenticated AES-CBC. A valid mnemonic checksum '
    'does not prove the ciphertext was not modified; verify the recovered '
    'addresses in your wallet.',
]


def looks_like_json(prefix):
    """Classify content, never a filename. The caller must reset its stream."""
    if prefix.startswith(b'\xef\xbb\xbf'):
        prefix = prefix[3:]
    return prefix.lstrip(b' \t\r\n').startswith(b'{')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryError('Duplicate fields in Skull Island JSON.')
        result[key] = value
    return result


def _hex(value, minimum, maximum, label):
    if (not isinstance(value, str) or len(value) % 2
            or not minimum * 2 <= len(value) <= maximum * 2
            or re.fullmatch(r'[0-9a-fA-F]+', value) is None):
        raise RecoveryError('Invalid Skull Island ' + label + '.')
    return bytes.fromhex(value)


def _read_document(stream):
    raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise RecoveryError('Skull Island JSON exceeds the recovery size limit.')
    try:
        text = raw.decode('utf-8-sig')
        data = json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=lambda unused: (_ for _ in ()).throw(
                              RecoveryError('Invalid JSON numeric value.')))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise RecoveryError('Invalid or truncated Skull Island JSON.') from None
    if not isinstance(data, dict) or not isinstance(data.get('settings'), dict):
        raise RecoveryError('Unsupported Skull Island JSON structure.')
    settings = data['settings']
    if settings.get('currentCoin') != 'pirate':
        raise RecoveryError('Unsupported Skull Island coin or network.')
    modern = settings.get('passPhrase')
    old = data.get('secretPhrase')
    if modern is not None and old is not None:
        raise RecoveryError('Ambiguous Skull Island seed fields.')
    cipher_text = modern if modern is not None else old
    if cipher_text is None:
        raise RecoveryError('Skull Island JSON does not contain an encrypted seed phrase.')
    verifier = _hex(settings.get('password'), 64, 64, 'password verifier')
    ciphertext = _hex(cipher_text, 16, MAX_CIPHERTEXT_BYTES, 'seed ciphertext')
    if len(ciphertext) % 16:
        raise RecoveryError('Invalid Skull Island seed ciphertext length.')
    return verifier, ciphertext, 'settings.passPhrase' if modern is not None else 'secretPhrase'


def recover_json(stream, password_provider):
    """Recover the mnemonic actually present in a Skull Island JSON backup.

    complete=True means all secret material in this *file* was recovered.
    scope='seed-only' and warnings deliberately prevent implying recovery of
    independent imports that are stored only in the separate native wallet.
    CBC's lack of authentication is not repaired by the password verifier.
    """
    verifier, ciphertext, schema = _read_document(stream)
    password = password_provider().encode('utf-8')
    actual = hmac.new(PW_SALT, password, hashlib.sha512).digest()
    if not hmac.compare_digest(verifier, actual):
        raise RecoveryError(PASSWORD_ERROR)
    material = hmac.new(KEY_SALT, password, hashlib.sha512).digest()
    # Keep optional AES imports here so help/format detection remain available
    # even when a source installation has not yet installed its dependencies.
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    try:
        decryptor = AES.new(material[:32], AES.MODE_CBC, iv=material[32:48])
        padded = decryptor.decrypt(ciphertext)
        seed = unpad(padded, AES.block_size, style='pkcs7').decode('utf-8')
    except (ValueError, UnicodeError):
        raise RecoveryError(PASSWORD_ERROR) from None
    words = seed.split(' ')
    if len(words) != 24 or not Mnemonic('english').check(seed):
        raise RecoveryError('Decrypted Skull Island seed is not a valid 24-word English mnemonic.')
    return {
        'seed': seed, 'outer': None, 'version': None, 'encrypted': True,
        'complete': True, 'error': None, 'shielded': [], 'transparent': [],
        'diversifiers': [], 'source': 'skull-island-json', 'scope': 'seed-only',
        'warnings': list(JSON_WARNINGS), 'json_schema': schema,
    }


def recover_binary(stream, password_provider, *, legacy_android_password=False):
    """Read source-verified raw Skull Island native bytes using the Lite parser.

    The optional old-Android mode is explicit, never a password search. In the
    pre-2.2 plugin, encryptionstatus set global args=[] and encrypt(arg) passed
    [args] instead of arg. Android getString(0) converted that array to '[]'.
    Sources: cordova-plugin-litewallet 9bf9264e77b11926cf54160d1d07f8061d841b2b,
    www/litewallet.js lines 45-48/89-91; src/android/LiteWallet.java encrypt.
    """
    provider = (lambda: '[]') if legacy_android_password else password_provider
    result = legacy.recover(stream, provider)
    result['source'] = 'skull-island-binary'
    result['scope'] = 'native-key-records'
    if legacy_android_password:
        result.setdefault('warnings', []).append(
            'The explicit pre-2.2 Android argument-bug mode was used. That '
            'version passed the literal [] to native encryption instead of '
            'the app password. Verify recovered addresses in your wallet.')
    return result
