"""Offline, read-only recovery of Pirate Wallet Lite seed and key records.

Format reference: PirateNetwork/piratewallet-light-cli commit
83f96539411ab70775c22fc0252c4460c2189489, lightwallet/{keys,walletzkey,wallettkey}.rs.
The reader does not validate transaction history or public curve points.
"""

import hashlib
import struct

from mnemonic import Mnemonic
from nacl.exceptions import CryptoError
from nacl.secret import SecretBox


class RecoveryError(Exception):
    """A safe diagnostic that contains no secret bytes or passwords."""


class Reader:
    def __init__(self, stream):
        self.stream = stream
        self.total = 0

    def take(self, size):
        if size < 0 or self.total + size > 8 * 1024 * 1024:
            raise RecoveryError('Key section exceeds the recovery size limit.')
        data = self.stream.read(size)
        self.total += len(data)
        if len(data) != size:
            raise RecoveryError('The key section is truncated.')
        return data

    def number(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def flag(self):
        value = self.number('<B')
        if value not in (0, 1):
            raise RecoveryError('Invalid key flag or option tag.')
        return bool(value)

    def compact(self, limit=10000):
        tag = self.number('<B')
        if tag < 253:
            value = tag
        else:
            fmt, minimum = {253: ('<H', 253), 254: ('<I', 65536),
                            255: ('<Q', 4294967296)}[tag]
            value = self.number(fmt)
            if value < minimum:
                raise RecoveryError('Non-canonical vector length.')
        if value > limit:
            raise RecoveryError('Key count or vector length exceeds the recovery limit.')
        return value

    def vector_bytes(self, limit=512):
        return self.take(self.compact(limit))

    def optional(self, read):
        return read() if self.flag() else None

    def string(self):
        size = self.number('<Q')
        if size > 512:
            raise RecoveryError('Address length exceeds the recovery limit.')
        try:
            text = self.take(size).decode('utf-8')
            if any(ord(c) < 32 or ord(c) > 126 for c in text):
                raise RecoveryError('Address contains invalid or non-printable characters.')
            return text
        except UnicodeError:
            raise RecoveryError('Invalid address text.') from None


def password_key(password):
    return hashlib.sha256(hashlib.sha256(password.encode('utf-8')).digest()).digest()


def open_secret(ciphertext, nonce, key, expected_size):
    if key is None or nonce is None or ciphertext is None:
        raise RecoveryError('Encrypted key data is missing.')
    if len(nonce) != 24 or len(ciphertext) != expected_size + 16:
        raise RecoveryError('Encrypted key or nonce has an invalid length.')
    try:
        return SecretBox(key).decrypt(ciphertext, nonce)
    except CryptoError:
        raise RecoveryError('Password is incorrect or encrypted data is damaged.') from None


def bech32(hrp, payload):
    # BIP-173, ordinary Bech32 (not Bech32m); Sapling permits long encodings.
    alphabet = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'
    data, accumulator, bits = [], 0, 0
    for byte in payload:
        accumulator = ((accumulator << 8) | byte) & 4095
        bits += 8
        while bits >= 5:
            bits -= 5
            data.append((accumulator >> bits) & 31)
    if bits:
        data.append((accumulator << (5 - bits)) & 31)
    values = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]
    check = 1
    for value in values + data + [0] * 6:
        top = check >> 25
        check = ((check & 0x1ffffff) << 5) ^ value
        for i, generator in enumerate((0x3b6a57b2, 0x26508e6d, 0x1ea119fa,
                                       0x3d4233dd, 0x2a1462b3)):
            if (top >> i) & 1:
                check ^= generator
    check ^= 1
    checksum = [(check >> (5 * (5 - i))) & 31 for i in range(6)]
    return hrp + '1' + ''.join(alphabet[n] for n in data + checksum)


def sapling_export(secret):
    modulus = 0x0e7db4ea6533afa906673b0101343b00a6682093ccc81082d0970e5ed6f72cb7
    if len(secret) != 169 or any(int.from_bytes(secret[start:start + 32], 'little') >= modulus
                                for start in (41, 73)):
        raise RecoveryError('Invalid Sapling spending-key scalar or length.')
    return bech32('secret-extended-key-main', secret)


def wif(secret):
    order = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141
    if len(secret) != 32 or not 0 < int.from_bytes(secret, 'big') < order:
        raise RecoveryError('Invalid transparent private key.')
    payload = b'\x80' + secret + b'\x01'
    data = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    value, encoded = int.from_bytes(data, 'big'), ''
    while value:
        value, digit = divmod(value, 58)
        encoded = alphabet[digit] + encoded
    return encoded


def header(reader):
    outer = reader.number('<Q')
    if not 1 <= outer <= 24:
        raise RecoveryError('Unsupported wallet format.')
    version = reader.number('<Q') if outer == 24 else outer
    if outer == 24 and not 1 <= version <= 21:
        raise RecoveryError('Unsupported key-section version.')
    encrypted = reader.flag() if outer >= 4 else False
    ciphertext = reader.take(48) if outer >= 4 else b''
    nonce = reader.vector_bytes(24) if outer >= 4 else b''
    stored_entropy = reader.take(32)
    if encrypted and len(nonce) != 24:
        raise RecoveryError('Encrypted seed nonce is damaged.')
    # Both the original v4 unlock/remove_encryption (72548e077ed199426ab239980f953151c73fb059,
    # 8ade7caa48268745fc40926c10b5adf21f7f83e6) and the pinned v24 Keys writer
    # initialize/clear enc_seed to 48 zero bytes and nonce to an empty vector.
    # A damaged encryption flag must not turn locked zero entropy into a false seed.
    if outer >= 4 and not encrypted and (ciphertext != bytes(48) or nonce):
        raise RecoveryError('Unencrypted seed header contains encrypted data; the encryption flag or header is damaged.')
    return outer, version, encrypted, ciphertext, nonce, stored_entropy


def key_record(reader, key, encrypted, shielded):
    if reader.number('<B') != 1:
        raise RecoveryError('Unsupported individual key version.')
    kind = reader.number('<I')
    if kind not in ((0, 1, 2) if shielded else (0, 1)):
        raise RecoveryError('Unsupported key type.')
    locked = reader.flag()
    size = 169 if shielded else 32
    clear = reader.optional(lambda: reader.take(size))
    public = reader.take(169) if shielded else reader.string()
    account = reader.optional(lambda: reader.number('<I'))
    ciphertext = reader.optional(reader.vector_bytes)
    nonce = reader.optional(reader.vector_bytes)
    # Pinned Wallet{Z,T}Key v1 constructors start unlocked, lock() removes
    # clear spending keys, and remove_encryption() removes imported cipher/nonce.
    # LightWallet::write refuses an encrypted, unlocked wallet. Inconsistent
    # records are not spending authority, even after the seed authenticates.
    if locked != encrypted or (encrypted and clear is not None):
        raise RecoveryError('Key lock state disagrees with wallet encryption.')
    if not encrypted and (ciphertext is not None or nonce is not None):
        raise RecoveryError('Unencrypted key record contains encrypted data.')
    if kind == 0 and (ciphertext is not None or nonce is not None):
        raise RecoveryError('HD key record unexpectedly contains encrypted key data.')
    if kind == 0:
        if account is None or account >= 0x80000000:
            raise RecoveryError('HD account index is missing or invalid.')
        if clear is None and not encrypted:
            raise RecoveryError('Unencrypted HD spending key is missing.')
    elif account is not None:
        raise RecoveryError('Imported key unexpectedly has an HD account index.')
    if kind == 1:
        if encrypted:
            recovered = open_secret(ciphertext, nonce, key, size)
            clear = recovered
        elif clear is None:
            raise RecoveryError('Imported spending key is missing.')
    if kind == 2 and (clear is not None or ciphertext is not None or nonce is not None):
        raise RecoveryError('Viewing-only record unexpectedly contains a spending key.')
    if shielded and clear is not None:
        # The shared metadata, OVK and diversifier key must agree. Public point
        # validation is performed by the destination wallet at import, not here.
        if clear[:41] != public[:41] or clear[105:] != public[105:]:
            raise RecoveryError('Spending and viewing key metadata disagree.')
    return {'kind': kind, 'account': account, 'locked': locked,
            'private': clear, 'public': public}


def export_record(record, shielded):
    if record['private'] is not None:
        record['export'] = sapling_export(record['private']) if shielded else wif(record['private'])
    else:
        record['export'] = None
    return record


def key_section(reader, outer, version, key, encrypted, result):
    # Append only complete, checked records. A damaged later record must not
    # discard an earlier imported spending key that the seed cannot recreate.
    shielded = result['shielded']
    transparent = result['transparent']
    diversifiers = result['diversifiers']
    if outer <= 6:
        private = []
        count = reader.compact()
        # The original v4 lock() emptied both private-key vectors; these
        # historical raw records have no separate authenticator to verify.
        if encrypted and count:
            raise RecoveryError('Encrypted legacy wallet contains clear spending keys.')
        for index in range(count):
            secret = reader.take(169)
            record = export_record({'kind': 0, 'account': index, 'locked': encrypted,
                                    'private': secret, 'public': None}, True)
            private.append(secret)
            shielded.append(record)
        public = []
        if outer >= 4:
            for index in range(reader.compact()):
                viewing = reader.take(169)
                public.append(viewing)
                if not private:
                    shielded.append(export_record({'kind': 0, 'account': index,
                                                   'locked': encrypted, 'private': None,
                                                   'public': viewing}, True))
                elif index < len(shielded):
                    secret = shielded[index]['private']
                    if secret[:41] != viewing[:41] or secret[105:] != viewing[105:]:
                        raise RecoveryError('Legacy spending and viewing key metadata disagree.')
                    shielded[index]['public'] = viewing
        if public and private and len(private) != len(public):
            raise RecoveryError('Legacy spending/viewing key counts disagree.')
    else:
        for _ in range(reader.compact()):
            shielded.append(export_record(key_record(reader, key, encrypted, True), True))
    if version <= 20:
        secrets, addresses = [], []
        count = reader.compact()
        if encrypted and count:
            raise RecoveryError('Encrypted legacy wallet contains clear transparent keys.')
        for index in range(count):
            secret = reader.take(32)
            transparent.append(export_record({'kind': 0, 'account': index,
                                               'private': secret, 'public': ''}, False))
            secrets.append(secret)
        if outer >= 4:
            for index in range(reader.compact()):
                address = reader.string()
                addresses.append(address)
                if not secrets:
                    transparent.append(export_record({'kind': 0, 'account': index,
                                                       'private': None, 'public': address}, False))
                elif index < len(transparent):
                    transparent[index]['public'] = address
        if addresses and secrets and len(addresses) != len(secrets):
            raise RecoveryError('Legacy transparent key/address counts disagree.')
    else:
        for _ in range(reader.compact()):
            transparent.append(export_record(key_record(reader, key, encrypted, False), False))
    if outer == 24 and version >= 21:
        for _ in range(reader.compact()):
            if reader.number('<Q') != 1:
                raise RecoveryError('Unsupported diversified-address version.')
            public = reader.take(169)
            reader.take(11)
            diversifiers.append((public, reader.string()))


def recover(stream, password_provider):
    reader = Reader(stream)
    outer, version, encrypted, cipher, nonce, entropy = header(reader)
    key = password_key(password_provider()) if encrypted else None
    if encrypted:
        entropy = open_secret(cipher, nonce, key, 32)
    seed = Mnemonic('english').to_mnemonic(entropy)
    result = {'seed': seed, 'outer': outer, 'version': version,
              'encrypted': encrypted, 'complete': False, 'error': None,
              'shielded': [], 'transparent': [], 'diversifiers': []}
    try:
        key_section(reader, outer, version, key, encrypted, result)
        result['complete'] = True
    except RecoveryError as error:
        result['error'] = str(error)
    result['source'] = 'lite'
    result['scope'] = 'seed-and-keys'
    result['warnings'] = []
    return result
