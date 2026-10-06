import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pirate_wallet_lite_recovery import cli
from pirate_wallet_lite_recovery.legacy import RecoveryError
from pirate_wallet_lite_recovery.self_test import run, synthetic_wallet


class CliTests(unittest.TestCase):
    def test_source_self_test_does_not_need_a_terminal_or_wallet(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(['--self-test']), 0)
        self.assertEqual(output.getvalue(), 'Self-test passed. No wallet files were read.\n')

    def test_recovery_refuses_piped_output_before_opening_file(self):
        with patch('sys.stdin.isatty', return_value=False), patch.object(Path, 'open') as opened:
            with self.assertRaisesRegex(RecoveryError, 'interactive terminal'):
                cli.main(['file-not-to-be-read.dat'])
            opened.assert_not_called()

    def test_legacy_password_option_is_format_scoped(self):
        with self.assertRaisesRegex(RecoveryError, 'requires --format'):
            cli.main(['--skull-island-legacy-password', 'test.dat'])

    def test_self_test_refuses_user_wallet_path(self):
        with self.assertRaisesRegex(RecoveryError, 'Do not supply'):
            cli.main(['--self-test', 'test.dat'])

    def test_matching_quotes_and_unicode_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wallet \u00e9\u96ea copy.dat'
            path.write_bytes(b'public synthetic test data')
            self.assertEqual(cli.normalise_path(str(path)), path)
            self.assertEqual(cli.normalise_path('"' + str(path) + '"'), path)
            self.assertEqual(cli.normalise_path("'" + str(path) + "'"), path)

    @unittest.skipIf(os.name == 'nt', 'Unix shell-escaped input')
    def test_unix_shell_escaped_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wallet with spaces.dat'
            path.write_bytes(b'public synthetic test data')
            self.assertEqual(cli.normalise_path(str(path).replace(' ', '\\ ')), path)

    def test_partial_output_keeps_recovered_keys_visible(self):
        from pirate_wallet_lite_recovery.legacy import recover
        from pirate_wallet_lite_recovery.self_test import _PUBLIC_SK, _PUBLIC_XFVK
        from test_legacy import fixture_header, key_record
        result = recover(io.BytesIO(fixture_header() + b'\x02' +
                                    key_record(1, _PUBLIC_SK, _PUBLIC_XFVK) + b'\x01'),
                         lambda: 'Public synthetic password: \u00e9\u96ea!')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            cli.display(result)
        self.assertIn('Partial recovery', output.getvalue())
        self.assertIn('secret-extended-key-main1', output.getvalue())

    def test_format_dispatch_reads_file_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wallet-copy.dat'
            raw = synthetic_wallet()
            path.write_bytes(raw)
            before = path.stat().st_mtime_ns
            result = cli.recover_file(path, lambda: 'public self-test password')
            self.assertTrue(result['complete'])
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(path.stat().st_mtime_ns, before)

    def test_json_output_does_not_imply_accounts_or_imported_keys_were_read(self):
        path = Path(__file__).parent / 'fixtures/skull_island/zero_wallet.json'
        result = cli.recover_file(path, lambda: 'Public Skull Island password: \u00e9\u96ea!')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            cli.display(result)
        self.assertEqual(result['scope'], 'seed-only')
        self.assertIn('Seed phrase recovered from the Skull Island JSON backup.', output.getvalue())
        self.assertIn('independently imported spending keys are not included', output.getvalue())
        self.assertNotIn('Record the seed account numbers', output.getvalue())


if __name__ == '__main__':
    unittest.main()
