import io
import json
import struct
import tempfile
import unittest
from pathlib import Path

from mnemonic import Mnemonic
from nacl.secret import SecretBox

from pirate_wallet_lite_recovery import legacy as recovery


PASSWORD = 'Public synthetic password: \u00e9\u96ea!'
ENTROPY = bytes(range(32))
NONCE = bytes(range(24))


def compact(n):
    if n < 253:
        return bytes([n])
    if n <= 65535:
        return b'\xfd' + struct.pack('<H', n)
    return b'\xfe' + struct.pack('<I', n)


def vector_bytes(value):
    return compact(len(value)) + value


def optional(value):
    return b'\x00' if value is None else b'\x01' + value


def text(value):
    raw = value.encode('utf-8')
    return struct.pack('<Q', len(raw)) + raw


def fixture_header(outer=24, version=21, encrypted=True, entropy=ENTROPY):
    result = struct.pack('<Q', outer)
    if outer == 24:
        result += struct.pack('<Q', version)
    if outer >= 4:
        # Match native new/remove_encryption: an unencrypted header has zero
        # enc_seed and no nonce, including v4 and the v24 Keys header.
        cipher = (SecretBox(recovery.password_key(PASSWORD)).encrypt(entropy, NONCE).ciphertext
                  if encrypted else bytes(48))
        result += bytes([encrypted]) + cipher + vector_bytes(NONCE if encrypted else b'')
    return result + (b'\x00' * 32 if encrypted else entropy)


def serialized_key_record(kind, private=None, public=b'\x00' * 169, account=None,
                          locked=True, shielded=True, cipher=None, nonce=None):
    result = bytes([1]) + struct.pack('<I', kind) + bytes([locked])
    result += optional(private)
    result += public if shielded else text(public)
    result += optional(struct.pack('<I', account) if account is not None else None)
    return result + optional(vector_bytes(cipher) if cipher is not None else None) + optional(vector_bytes(nonce) if nonce is not None else None)


def key_record(kind, private=None, public=b'\x00' * 169, account=None,
               encrypted=True, shielded=True):
    cipher = None
    if encrypted and kind == 1 and private is not None:
        cipher = SecretBox(recovery.password_key(PASSWORD)).encrypt(private, NONCE).ciphertext
    # Native WalletZKey::lock also marks viewing-only records locked; this
    # is status metadata, never proof that a viewing record can spend.
    return serialized_key_record(kind, private if not encrypted else None, public, account,
                                 encrypted, shielded, cipher, NONCE if cipher is not None else None)


def empty_wallet(outer=24, version=21, encrypted=True):
    vectors = b'\x00' * (3 if outer == 24 and version >= 21 else
                         (4 if 4 <= outer <= 6 else 3 if outer <= 20 else 2))
    return fixture_header(outer, version, encrypted) + vectors


def native_fixture_wallet(outer=24, encrypted=True):
    fixture = json.loads((Path(__file__).parent / 'fixtures/native_sdk_keys.json').read_text())
    keys = {key['label']: key for key in fixture['keys']}
    records = b''
    for label, kind, account in [('primary_account_0', 0, 0), ('primary_account_7', 0, 7),
                                 ('imported_account_0', 1, None)]:
        native = keys[label]
        records += key_record(kind, bytes.fromhex(native['sk_hex']),
                              bytes.fromhex(native['xfvk_hex']), account, encrypted)
    records += key_record(2, public=bytes.fromhex(keys['imported_account_0']['xfvk_hex']),
                          encrypted=encrypted)
    return fixture_header(outer, encrypted=encrypted, entropy=bytes(32)) + b'\x04' + records + (b'\x00\x00' if outer == 24 else b'\x00')


class RecoveryTests(unittest.TestCase):
    def recover(self, raw, password=PASSWORD):
        return recovery.recover(io.BytesIO(raw), lambda: password)

    def test_encrypted_all_supported_outer_versions(self):
        for outer in range(4, 25):
            with self.subTest(outer=outer):
                result = self.recover(empty_wallet(outer))
                self.assertTrue(result['complete'])
                self.assertEqual(Mnemonic('english').to_entropy(result['seed']), ENTROPY)

    def test_unencrypted_legacy_without_crypto_header(self):
        for outer in range(1, 4):
            result = recovery.recover(io.BytesIO(empty_wallet(outer, encrypted=False)),
                                      lambda: self.fail('Should not prompt for a password'))
            self.assertTrue(result['complete'])
            self.assertEqual(Mnemonic('english').to_entropy(result['seed']), ENTROPY)

    def test_unencrypted_crypto_headers_match_native_cleared_state(self):
        for outer in range(4, 25):
            with self.subTest(outer=outer):
                result = recovery.recover(io.BytesIO(empty_wallet(outer, encrypted=False)),
                                          lambda: self.fail('Should not prompt for a password'))
                self.assertTrue(result['complete'], result['error'])
                self.assertEqual(Mnemonic('english').to_entropy(result['seed']), ENTROPY)

    def test_damaged_encryption_flag_cannot_generate_false_zero_seed(self):
        for outer in range(4, 25):
            with self.subTest(outer=outer):
                raw = bytearray(empty_wallet(outer))
                raw[16 if outer == 24 else 8] = 0
                with self.assertRaisesRegex(recovery.RecoveryError, 'Unencrypted seed header'):
                    recovery.recover(io.BytesIO(raw),
                                     lambda: self.fail('Header validation must precede password prompt'))

    def test_unencrypted_header_rejects_stale_cipher_or_nonce_separately(self):
        for outer in (4, 6, 7, 20, 21, 23, 24):
            offset = 16 if outer == 24 else 8
            cleared = fixture_header(outer, encrypted=False)
            stale_cipher = cleared[:offset + 1] + bytes([1]) + cleared[offset + 2:]
            stale_nonce = (cleared[:offset + 49] + vector_bytes(NONCE)
                           + cleared[offset + 50:])
            for raw in (stale_cipher, stale_nonce):
                with self.subTest(outer=outer, has_nonce=raw is stale_nonce):
                    with self.assertRaisesRegex(recovery.RecoveryError, 'Unencrypted seed header'):
                        self.recover(raw)

    def test_encrypted_seed_never_uses_nonzero_stored_plaintext_entropy(self):
        raw = fixture_header()[:-32] + bytes(reversed(range(32))) + b'\x00' * 3
        result = self.recover(raw)
        self.assertTrue(result['complete'])
        self.assertEqual(Mnemonic('english').to_entropy(result['seed']), ENTROPY)

    def test_known_bip39_vector(self):
        raw = fixture_header(encrypted=False)[:-32] + b'\x00' * 32 + b'\x00' * 3
        self.assertEqual(self.recover(raw)['seed'], ' '.join(['abandon'] * 23 + ['art']))

    def test_wrong_password_and_corrupt_authenticator(self):
        raw = empty_wallet()
        for candidate, password in [(raw, 'wrong'), (raw[:17] + bytes([raw[17] ^ 1]) + raw[18:], PASSWORD)]:
            with self.assertRaisesRegex(recovery.RecoveryError, 'incorrect or encrypted data is damaged'):
                self.recover(candidate, password)

    def test_truncated_seed_does_not_generate_mnemonic(self):
        with self.assertRaisesRegex(recovery.RecoveryError, 'truncated'):
            self.recover(fixture_header()[:40])

    def test_damaged_tail_is_explicit_partial_recovery(self):
        result = self.recover(fixture_header() + b'\x01')
        self.assertFalse(result['complete'])
        self.assertIn('truncated', result['error'])
        self.assertEqual(Mnemonic('english').to_entropy(result['seed']), ENTROPY)
        self.assertEqual(result['shielded'], [])

    def test_blockchain_cache_not_read(self):
        stream = io.BytesIO(empty_wallet() + b'DAMAGED TX CACHE THAT MUST NOT BE PARSED')
        result = recovery.recover(stream, lambda: PASSWORD)
        self.assertTrue(result['complete'])
        self.assertEqual(stream.tell(), len(empty_wallet()))

    def test_unknown_versions_rejected(self):
        for raw in [struct.pack('<Q', 0), struct.pack('<Q', 25),
                    struct.pack('<QQ', 24, 22)]:
            with self.assertRaisesRegex(recovery.RecoveryError, 'Unsupported'):
                self.recover(raw)

    def test_option_flags_and_noncanonical_compactsize_rejected(self):
        for raw in [b'\x02', b'\xfd\x01\x00', b'\xfe\xff\xff\x00\x00', b'\xff' + struct.pack('<Q', 1)]:
            reader = recovery.Reader(io.BytesIO(raw))
            with self.assertRaises(recovery.RecoveryError):
                reader.flag() if raw == b'\x02' else reader.compact()

    def test_vector_bounds(self):
        result = self.recover(fixture_header() + compact(10001))
        self.assertFalse(result['complete'])
        self.assertIn('limit', result['error'])

    def test_key_type_and_record_version_rejected(self):
        for record in [bytes([2]), bytes([1]) + struct.pack('<I', 3)]:
            result = self.recover(fixture_header() + b'\x01' + record)
            self.assertFalse(result['complete'])
            self.assertIn('Unsupported', result['error'])

    def test_hd_and_viewing_records_preserve_scope(self):
        records = key_record(0, account=7) + key_record(2)
        result = self.recover(fixture_header() + b'\x02' + records + b'\x00\x00')
        self.assertTrue(result['complete'])
        self.assertEqual(result['shielded'][0]['account'], 7)
        self.assertIsNone(result['shielded'][0]['export'])
        self.assertEqual(result['shielded'][1]['kind'], 2)
        self.assertIsNone(result['shielded'][1]['export'])

    def test_mixed_spending_key_states_are_partial_and_never_exported(self):
        private_z = bytes(169)
        private_t = (1).to_bytes(32, 'big')
        for shielded in (True, False):
            private = private_z if shielded else private_t
            public = bytes(169) if shielded else 'synthetic-address'
            for encrypted in (True, False):
                for kind in (0, 1):
                    account = 0 if kind == 0 else None
                    cipher = (SecretBox(recovery.password_key(PASSWORD)).encrypt(private, NONCE).ciphertext
                              if encrypted and kind == 1 else None)
                    nonce = NONCE if cipher is not None else None
                    invalid = [
                        serialized_key_record(kind, None if encrypted else private, public, account,
                                              not encrypted, shielded, cipher, nonce),
                    ]
                    if encrypted:
                        invalid.append(serialized_key_record(kind, private, public, account,
                                                             True, shielded, cipher, nonce))
                    else:
                        invalid.extend([
                            serialized_key_record(kind, private, public, account, False,
                                                  shielded, bytes(48), None),
                            serialized_key_record(kind, private, public, account, False,
                                                  shielded, None, NONCE),
                        ])
                    if kind == 0 and encrypted:
                        invalid.extend([
                            serialized_key_record(kind, None, public, account, True,
                                                  shielded, bytes(48), None),
                            serialized_key_record(kind, None, public, account, True,
                                                  shielded, None, NONCE),
                        ])
                    for record in invalid:
                        with self.subTest(shielded=shielded, encrypted=encrypted, kind=kind):
                            prefix = b'\x01' if shielded else b'\x00\x01'
                            result = self.recover(fixture_header(encrypted=encrypted) + prefix + record)
                            self.assertFalse(result['complete'])
                            self.assertEqual(result['shielded'], [])
                            self.assertEqual(result['transparent'], [])
                            self.assertEqual(Mnemonic('english').to_entropy(result['seed']), ENTROPY)

    def test_viewing_only_records_reject_spending_or_encryption_fields(self):
        for encrypted in (True, False):
            for fields in ({'private': bytes(169)}, {'cipher': bytes(185)}, {'nonce': NONCE}):
                record = serialized_key_record(2, locked=encrypted, **fields)
                result = self.recover(fixture_header(encrypted=encrypted) + b'\x01' + record)
                self.assertFalse(result['complete'])
                self.assertEqual(result['shielded'], [])

    def test_encrypted_legacy_vectors_never_export_clear_spending_keys(self):
        for outer in range(4, 7):
            result = self.recover(fixture_header(outer) + b'\x01' + bytes(169))
            self.assertFalse(result['complete'])
            self.assertIn('clear spending keys', result['error'])
            self.assertEqual(result['shielded'], [])
        for outer in range(4, 21):
            # Old shielded vectors are SK/FVK; later versions have one ZKey vector.
            prefix = b'\x00\x00' if outer <= 6 else b'\x00'
            result = self.recover(fixture_header(outer) + prefix + b'\x01' + (1).to_bytes(32, 'big'))
            self.assertFalse(result['complete'])
            self.assertIn('clear transparent keys', result['error'])
            self.assertEqual(result['transparent'], [])

    def test_imported_spending_key_decrypted_not_derived_from_seed(self):
        private = bytes(range(41)) + (1).to_bytes(32, 'little') * 2 + bytes(range(105, 169))
        public = private[:41] + bytes([123]) * 64 + private[105:]
        record = key_record(1, private, public)
        result = self.recover(fixture_header() + b'\x01' + record + b'\x00\x00')
        self.assertTrue(result['complete'])
        self.assertEqual(result['shielded'][0]['private'], private)
        self.assertTrue(result['shielded'][0]['export'].startswith('secret-extended-key-main1'))

    def test_imported_key_metadata_mismatch_is_partial(self):
        record = key_record(1, bytes(range(169)))
        result = self.recover(fixture_header() + b'\x01' + record + b'\x00\x00')
        self.assertFalse(result['complete'])
        self.assertIn('metadata disagree', result['error'])

    def test_noncanonical_sapling_scalar_is_partial(self):
        private = bytes(range(169))
        public = private[:41] + bytes(64) + private[105:]
        result = self.recover(fixture_header() + b'\x01' + key_record(1, private, public) + b'\x00\x00')
        self.assertFalse(result['complete'])
        self.assertIn('scalar', result['error'])

    def test_terminal_control_characters_are_rejected(self):
        record = key_record(1, (1).to_bytes(32, 'big'), '\x1b[2J', shielded=False)
        result = self.recover(fixture_header() + b'\x00\x01' + record + b'\x00')
        self.assertFalse(result['complete'])
        self.assertIn('non-printable', result['error'])

    def test_corrupt_imported_cipher_is_partial(self):
        record = bytearray(key_record(1, b'\x00' * 169))
        record[-26] ^= 1
        result = self.recover(fixture_header() + b'\x01' + record + b'\x00\x00')
        self.assertFalse(result['complete'])

    def test_imported_transparent_key_and_wif_known_vector(self):
        private = (1).to_bytes(32, 'big')
        record = key_record(1, private, 'legacy-address', shielded=False)
        result = self.recover(fixture_header() + b'\x00\x01' + record + b'\x00')
        self.assertTrue(result['complete'])
        self.assertEqual(result['transparent'][0]['export'],
                         'KwDiBf89QgGbjEhKnhXJuH7LrciVrZi3qYjgd9M7rFU73sVHnoWn')

    def test_invalid_transparent_scalar_is_partial(self):
        record = key_record(1, b'\x00' * 32, 'legacy-address', shielded=False)
        result = self.recover(fixture_header() + b'\x00\x01' + record + b'\x00')
        self.assertFalse(result['complete'])
        self.assertIn('Invalid transparent', result['error'])

    def test_diversified_records_parsed_only_in_key_section(self):
        div = struct.pack('<Q', 1) + b'\x00' * 169 + b'\x00' * 11 + text('synthetic-address')
        result = self.recover(fixture_header() + b'\x00\x00\x01' + div)
        self.assertTrue(result['complete'])
        self.assertEqual(result['diversifiers'][0][1], 'synthetic-address')

    def test_input_file_content_and_mtime_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic-wallet.dat'
            path.write_bytes(empty_wallet())
            before = path.stat().st_mtime_ns
            with path.open('rb') as stream:
                self.assertTrue(recovery.recover(stream, lambda: PASSWORD)['complete'])
            self.assertEqual(path.read_bytes(), empty_wallet())
            self.assertEqual(path.stat().st_mtime_ns, before)

    def test_password_not_in_diagnostics(self):
        try:
            self.recover(empty_wallet(), 'secret-password-never-log')
        except recovery.RecoveryError as error:
            self.assertNotIn('secret-password-never-log', str(error))

    def test_valid_imported_keys_survive_a_damaged_later_record(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/native_sdk_keys.json').read_text())
        imported = next(key for key in fixture['keys'] if key['label'] == 'imported_account_0')
        valid = key_record(1, bytes.fromhex(imported['sk_hex']), bytes.fromhex(imported['xfvk_hex']))
        raw = fixture_header() + b'\x02' + valid + b'\x01'
        result = self.recover(raw)
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['shielded']), 1)
        self.assertEqual(result['shielded'][0]['export'], imported['sk_bech32'])

    def test_valid_imported_key_survives_a_later_inconsistent_clear_hd_key(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/native_sdk_keys.json').read_text())
        imported = next(key for key in fixture['keys'] if key['label'] == 'imported_account_0')
        secret, public = bytes.fromhex(imported['sk_hex']), bytes.fromhex(imported['xfvk_hex'])
        valid = key_record(1, secret, public)
        invalid = serialized_key_record(0, secret, public, account=0)
        result = self.recover(fixture_header() + b'\x02' + valid + invalid)
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['shielded']), 1)
        self.assertEqual(result['shielded'][0]['export'], imported['sk_bech32'])
        self.assertEqual(Mnemonic('english').to_entropy(result['seed']), ENTROPY)

    def test_valid_imported_keys_survive_a_damaged_transparent_section(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/native_sdk_keys.json').read_text())
        imported = next(key for key in fixture['keys'] if key['label'] == 'imported_account_0')
        valid = key_record(1, bytes.fromhex(imported['sk_hex']), bytes.fromhex(imported['xfvk_hex']))
        result = self.recover(fixture_header() + b'\x01' + valid + b'\x01')
        self.assertFalse(result['complete'])
        self.assertEqual(result['shielded'][0]['export'], imported['sk_bech32'])

    def test_native_sdk_encoding_interoperability(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/native_sdk_keys.json').read_text())
        for native in fixture['keys']:
            self.assertEqual(recovery.sapling_export(bytes.fromhex(native['sk_hex'])), native['sk_bech32'])
            self.assertEqual(recovery.bech32('zxviews', bytes.fromhex(native['xfvk_hex'])), native['xfvk_bech32'])

    def test_real_native_sdk_keys_in_legacy_wallet_records(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/native_sdk_keys.json').read_text())
        imported = next(key for key in fixture['keys'] if key['label'] == 'imported_account_0')
        for outer in (21, 24):
            for encrypted in (False, True):
                result = self.recover(native_fixture_wallet(outer, encrypted))
                self.assertTrue(result['complete'], result['error'])
                self.assertEqual(result['seed'], ' '.join(['abandon'] * 23 + ['art']))
                self.assertEqual([key['account'] for key in result['shielded'][:2]], [0, 7])
                self.assertEqual(result['shielded'][2]['export'], imported['sk_bech32'])
                self.assertIsNone(result['shielded'][3]['export'])


if __name__ == '__main__':
    unittest.main()
