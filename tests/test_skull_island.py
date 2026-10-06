import hashlib
import hmac
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from nacl.secret import SecretBox

from pirate_wallet_lite_recovery import legacy, skull_island
from pirate_wallet_lite_recovery.legacy import RecoveryError


FIXTURES = Path(__file__).parent / 'fixtures' / 'skull_island'
PASSWORD = 'Public Skull Island password: é雪!'
SEED = ' '.join(['abandon'] * 23 + ['art'])
NONCE = bytes(range(24))


def native_key_prefix(password=PASSWORD, truncated=False):
    """Source-compatible public native key prefix, with independent imports."""
    fixture = json.loads((FIXTURES.parent / 'native_sdk_keys.json').read_text('utf-8'))
    imported = next(item for item in fixture['keys'] if item['label'] == 'imported_account_0')
    secret = bytes.fromhex(imported['sk_hex'])
    public = bytes.fromhex(imported['xfvk_hex'])
    key = legacy.password_key(password)
    cipher = SecretBox(key).encrypt(bytes(32), NONCE).ciphertext
    header = struct.pack('<QQB', 24, 21, 1) + cipher + bytes([24]) + NONCE + bytes(32)
    # Current WalletZKey writer: version/type/locked, no clear SK, FVK,
    # no HD index, optional compact ciphertext, optional compact nonce.
    encrypted = SecretBox(key).encrypt(secret, NONCE).ciphertext
    record = (struct.pack('<BIB', 1, 1, 1) + b'\x00' + public + b'\x00'
              + b'\x01' + bytes([len(encrypted)]) + encrypted
              + b'\x01\x18' + NONCE)
    raw = header + b'\x01' + record + b'\x00\x00'
    return raw[:-1] if truncated else raw


class SkullIslandTests(unittest.TestCase):
    def fixture(self, name='zero_wallet.json'):
        return json.loads((FIXTURES / name).read_text('utf-8'))

    def recover_document(self, data, password=PASSWORD):
        return skull_island.recover_json(io.BytesIO(json.dumps(data).encode('utf-8')),
                                        lambda: password)

    def test_modern_node_writer_fixture_and_unicode_password(self):
        provider = Mock(return_value=PASSWORD)
        with (FIXTURES / 'zero_wallet.json').open('rb') as stream:
            result = skull_island.recover_json(stream, provider)
        self.assertEqual(result['seed'], SEED)
        self.assertTrue(result['complete'])
        self.assertEqual(result['scope'], 'seed-only')
        self.assertEqual(result['source'], 'skull-island-json')
        self.assertEqual(result['json_schema'], 'settings.passPhrase')
        self.assertEqual(result['shielded'], [])
        self.assertTrue(any('imported spending keys' in item for item in result['warnings']))
        self.assertTrue(any('unauthenticated AES-CBC' in item for item in result['warnings']))
        provider.assert_called_once_with()

    def test_old_top_level_secret_phrase_writer_fixture(self):
        result = self.recover_document(self.fixture('old_zero_wallet.json'))
        self.assertEqual(result['seed'], SEED)
        self.assertEqual(result['json_schema'], 'secretPhrase')

    def test_password_salt_is_ascii_not_hex(self):
        expected = bytes.fromhex(self.fixture()['settings']['password'])
        actual = hmac.new(skull_island.PW_SALT, PASSWORD.encode(), hashlib.sha512).digest()
        incorrectly_decoded = hmac.new(bytes.fromhex(skull_island.PW_SALT.decode()),
                                      PASSWORD.encode(), hashlib.sha512).digest()
        self.assertEqual(actual, expected)
        self.assertNotEqual(incorrectly_decoded, expected)

    def test_password_verifier_uses_constant_time_comparison(self):
        from unittest.mock import patch
        with patch.object(skull_island.hmac, 'compare_digest', wraps=hmac.compare_digest) as compare:
            self.recover_document(self.fixture())
        compare.assert_called_once()

    def test_wrong_password_never_discloses_secrets(self):
        with self.assertRaises(RecoveryError) as error:
            self.recover_document(self.fixture(), 'Incorrect public password')
        self.assertEqual(str(error.exception), skull_island.PASSWORD_ERROR)
        self.assertNotIn(PASSWORD, str(error.exception))
        self.assertNotIn('abandon', str(error.exception))

    def test_tampered_cbc_padding_fails(self):
        data = self.fixture()
        cipher = bytearray.fromhex(data['settings']['passPhrase'])
        cipher[-17] ^= 0x80
        data['settings']['passPhrase'] = cipher.hex()
        with self.assertRaisesRegex(RecoveryError, 'backup is damaged'):
            self.recover_document(data)

    def test_ciphertext_tampering_cannot_bypass_mnemonic_validation(self):
        data = self.fixture()
        cipher = bytearray.fromhex(data['settings']['passPhrase'])
        cipher[0] ^= 0x01
        data['settings']['passPhrase'] = cipher.hex()
        with self.assertRaises(RecoveryError):
            self.recover_document(data)

    def test_damaged_password_verifier_fails(self):
        data = self.fixture()
        data['settings']['password'] = '00' * 64
        with self.assertRaisesRegex(RecoveryError, 'backup is damaged'):
            self.recover_document(data)

    def test_plaintext_or_invented_seed_fields_not_accepted(self):
        for change in ({'passPhrase': SEED}, {'seed': SEED, 'passPhrase': None},
                       {'passPhrase': 'zz'}, {'passPhrase': 'aa' * 17}):
            data = self.fixture()
            data['settings'].update(change)
            with self.subTest(change=change), self.assertRaises(RecoveryError):
                self.recover_document(data)

    def test_unsupported_coin_checked_before_password(self):
        data = self.fixture()
        data['settings']['currentCoin'] = 'zero'
        provider = Mock(side_effect=AssertionError('must not ask'))
        with self.assertRaisesRegex(RecoveryError, 'coin or network'):
            skull_island.recover_json(io.BytesIO(json.dumps(data).encode()), provider)
        provider.assert_not_called()

    def test_ambiguous_schemas_rejected(self):
        data = self.fixture()
        data['secretPhrase'] = data['settings']['passPhrase']
        with self.assertRaisesRegex(RecoveryError, 'Ambiguous'):
            self.recover_document(data)

    def test_duplicate_fields_rejected_without_printing_contents(self):
        raw = b'{"settings":{},"settings":{"private":"do not print this"}}'
        with self.assertRaisesRegex(RecoveryError, '^Duplicate fields') as error:
            skull_island.recover_json(io.BytesIO(raw), lambda: PASSWORD)
        self.assertNotIn('do not print', str(error.exception))

    def test_invalid_truncated_and_oversized_json(self):
        for raw in (b'{}', b'[]', b'{"settings":', b'\xff',
                    b'x' * (skull_island.MAX_JSON_BYTES + 1)):
            with self.subTest(size=len(raw)), self.assertRaises(RecoveryError):
                skull_island.recover_json(io.BytesIO(raw), lambda: PASSWORD)

    def test_bom_and_whitespace_content_detection(self):
        for prefix in (b'{', b' \t\n{', b'\xef\xbb\xbf\r\n{'):
            self.assertTrue(skull_island.looks_like_json(prefix))
        self.assertFalse(skull_island.looks_like_json(struct.pack('<Q', 24)))
        raw = b'\xef\xbb\xbf' + (FIXTURES / 'zero_wallet.json').read_bytes()
        self.assertEqual(skull_island.recover_json(io.BytesIO(raw), lambda: PASSWORD)['seed'], SEED)

    def test_json_input_file_not_changed(self):
        raw = (FIXTURES / 'zero_wallet.json').read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Public synthetic é雪 wallet copy.json'
            path.write_bytes(raw)
            before = hashlib.sha256(path.read_bytes()).digest()
            with path.open('rb') as stream:
                skull_island.recover_json(stream, lambda: PASSWORD)
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), before)

    def test_native_raw_bytes_preserve_independently_imported_key(self):
        result = skull_island.recover_binary(io.BytesIO(native_key_prefix()), lambda: PASSWORD)
        self.assertEqual(result['seed'], SEED)
        self.assertEqual(result['source'], 'skull-island-binary')
        self.assertEqual(result['scope'], 'native-key-records')
        self.assertTrue(result['complete'])
        self.assertEqual(result['shielded'][0]['kind'], 1)
        self.assertTrue(result['shielded'][0]['export'].startswith('secret-extended-key-main1'))

    def test_native_base64_transport_is_not_mistaken_for_file_bytes(self):
        import base64
        raw = base64.b64encode(native_key_prefix())
        with self.assertRaisesRegex(RecoveryError, 'Unsupported wallet format'):
            skull_island.recover_binary(io.BytesIO(raw), lambda: PASSWORD)

    def test_native_hash_as_password_not_invented(self):
        raw = native_key_prefix()
        hash_text = self.fixture()['settings']['password']
        with self.assertRaises(RecoveryError):
            skull_island.recover_binary(io.BytesIO(raw), lambda: hash_text)

    def test_old_android_literal_password_requires_explicit_mode(self):
        raw = native_key_prefix(password='[]')
        with self.assertRaises(RecoveryError):
            skull_island.recover_binary(io.BytesIO(raw), lambda: PASSWORD)
        provider = Mock(side_effect=AssertionError('legacy mode must not use app password'))
        result = skull_island.recover_binary(io.BytesIO(raw), provider,
                                            legacy_android_password=True)
        self.assertEqual(result['seed'], SEED)
        self.assertTrue(result['complete'])
        self.assertIn('literal []', result['warnings'][0])
        provider.assert_not_called()

    def test_native_partial_recovery_keeps_authenticated_seed(self):
        result = skull_island.recover_binary(io.BytesIO(native_key_prefix(truncated=True)),
                                            lambda: PASSWORD)
        self.assertEqual(result['seed'], SEED)
        self.assertFalse(result['complete'])
        self.assertIsNotNone(result['error'])


if __name__ == '__main__':
    unittest.main()
