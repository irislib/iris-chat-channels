"""Offline first-run installation, integrity, and restart contracts."""
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from hermes import transport


def archive(binary=b'#!/bin/sh\necho "iris 2026.10.30"\n', kind=tarfile.REGTYPE):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as bundle:
        member = tarfile.TarInfo('iris/iris')
        member.type = kind
        member.linkname = '/unrelated/file' if kind == tarfile.SYMTYPE else ''
        member.size = len(binary) if kind == tarfile.REGTYPE else 0
        bundle.addfile(member, io.BytesIO(binary) if member.size else None)
    return output.getvalue()


class InstallContract(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / 'channel'
        def enter(context):
            value = context.__enter__()
            self.addCleanup(context.__exit__, None, None, None)
            return value
        self.enter = enter
        self.enter(patch.dict(os.environ, {'PATH': str(self.root / 'empty-path')}))
        self.enter(patch('hermes.transport.platform.system', return_value='Darwin'))
        self.enter(patch('hermes.transport.platform.machine', return_value='arm64'))
        self.payload = archive()
        self.enter(patch.dict(transport.IRIS_RELEASES, {
            ('Darwin', 'arm64'): ('aarch64-apple-darwin', hashlib.sha256(self.payload).hexdigest())
        }))
        self.download = self.enter(patch('hermes.transport.urllib.request.urlopen',
            side_effect=lambda *args, **kwargs: io.BytesIO(self.payload)))
        self.prompt = self.enter(patch('builtins.input', return_value='y'))

    def test_missing_installs_once_and_restarts_without_path_or_network(self):
        binary = transport.ensure_iris(self.state)
        self.assertEqual(binary, str(self.state / 'bin/iris'))
        self.assertTrue(os.access(binary, os.X_OK))
        self.assertIn('/v2026.10.30/iris-v2026.10.30-aarch64-apple-darwin.tar.gz', self.download.call_args.args[0])
        self.assertEqual(transport.Transport(self.state).binary, binary)
        self.assertEqual(transport.ensure_iris(self.state), binary)
        self.assertEqual(self.download.call_count, 1)
        self.assertEqual(self.prompt.call_count, 1)
        self.assertFalse((self.state / 'profile').exists())
        self.assertEqual(list(self.state.glob('.iris-install-*')), [])

    def test_existing_install_is_persisted_without_download_or_prompt(self):
        binary = self.root / 'iris'
        binary.write_text('#!/bin/sh\necho "iris 2026.11.1"\n')
        binary.chmod(0o755)
        with patch.dict(os.environ, {'PATH': str(self.root)}):
            self.assertEqual(transport.ensure_iris(self.state), str(binary))
        self.assertEqual(transport.Transport(self.state).binary, str(binary))
        self.prompt.assert_not_called()
        self.download.assert_not_called()

    def test_decline_or_closed_input_does_not_download_or_create_profile(self):
        for reply in ('n', EOFError()):
            self.prompt.side_effect = reply if isinstance(reply, Exception) else None
            self.prompt.return_value = reply
            with self.assertRaises(transport.IrisInstallError):
                transport.ensure_iris(self.state)
        self.download.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_hash_mismatch_never_executes_or_installs(self):
        self.payload = archive(b'wrong bytes')
        with patch('hermes.transport.subprocess.run') as execute:
            with self.assertRaisesRegex(transport.IrisInstallError, 'checksum'):
                transport.ensure_iris(self.state)
            execute.assert_not_called()
        self.assertFalse((self.state / 'bin/iris').exists())
        self.assertFalse((self.state / 'cli.json').exists())

    def test_archive_symlink_is_rejected_without_execution(self):
        self.payload = archive(kind=tarfile.SYMTYPE)
        transport.IRIS_RELEASES[('Darwin', 'arm64')] = ('aarch64-apple-darwin', hashlib.sha256(self.payload).hexdigest())
        with patch('hermes.transport.subprocess.run') as execute:
            with self.assertRaisesRegex(transport.IrisInstallError, 'archive'):
                transport.ensure_iris(self.state)
            execute.assert_not_called()

    def test_explicit_missing_binary_does_not_fall_back(self):
        with self.assertRaisesRegex(transport.IrisInstallError, 'configured'):
            transport.ensure_iris(self.state, '/missing/custom-iris')
        self.download.assert_not_called()
        self.prompt.assert_not_called()

    def test_missing_saved_binary_does_not_replace_existing_identity(self):
        self.state.mkdir()
        (self.state / 'cli.json').write_text(json.dumps({'path': '/missing/saved-iris'}))
        (self.state / 'pairing.json').write_text('existing contact')
        with self.assertRaisesRegex(transport.IrisInstallError, 'configured'):
            transport.ensure_iris(self.state)
        self.assertEqual((self.state / 'pairing.json').read_text(), 'existing contact')
        self.download.assert_not_called()

    def test_broken_existing_binary_is_not_replaced(self):
        binary = self.root / 'iris'
        binary.write_text('#!/bin/sh\nexit 1\n')
        binary.chmod(0o755)
        with patch.dict(os.environ, {'PATH': str(self.root)}):
            with self.assertRaises(transport.IrisInstallError):
                transport.ensure_iris(self.state)
        self.assertEqual(binary.read_text(), '#!/bin/sh\nexit 1\n')
        self.download.assert_not_called()

    def test_unsupported_platform_is_actionable_without_download(self):
        with patch('hermes.transport.platform.machine', return_value='unsupported'):
            with self.assertRaisesRegex(transport.IrisInstallError, 'install.*Iris.*yourself'):
                transport.ensure_iris(self.state)
        self.download.assert_not_called()
        self.prompt.assert_not_called()

    def test_gateway_start_never_installs_or_prompts(self):
        self.assertEqual(transport.Transport(self.state).binary, 'iris')
        self.download.assert_not_called()
        self.prompt.assert_not_called()

    def test_download_failure_can_be_retried_without_changing_profile(self):
        self.state.mkdir()
        (self.state / 'pairing.json').write_text('existing contact')
        self.download.side_effect = OSError('offline')
        with self.assertRaisesRegex(transport.IrisInstallError, 'internet connection'):
            transport.ensure_iris(self.state)
        self.assertFalse((self.state / 'cli.json').exists())
        self.assertFalse((self.state / 'bin/iris').exists())
        self.download.side_effect = lambda *args, **kwargs: io.BytesIO(self.payload)
        binary = transport.ensure_iris(self.state)
        self.assertTrue(Path(binary).exists())
        self.assertEqual((self.state / 'pairing.json').read_text(), 'existing contact')

    def test_explicit_binary_wins_over_saved_location(self):
        transport.ensure_iris(self.state)
        self.assertEqual(transport.Transport(self.state, '/chosen/iris').binary, '/chosen/iris')

    def test_concurrent_setup_does_not_download_or_replace(self):
        self.state.mkdir()
        with (self.state / 'install.lock').open('a') as lock:
            transport.fcntl.flock(lock, transport.fcntl.LOCK_EX | transport.fcntl.LOCK_NB)
            with self.assertRaisesRegex(transport.IrisInstallError, 'Another Iris setup'):
                transport.ensure_iris(self.state)
        self.download.assert_not_called()

    def test_release_pins_cover_supported_mac_and_linux_hosts(self):
        self.assertEqual(set(transport.IRIS_RELEASES), {
            ('Darwin', 'arm64'), ('Darwin', 'x86_64'), ('Linux', 'x86_64')})
        for target, digest in transport.IRIS_RELEASES.values():
            self.assertEqual(len(bytes.fromhex(digest)), 32)


if __name__ == '__main__':
    unittest.main()
