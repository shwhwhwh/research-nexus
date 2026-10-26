import copy
import json
from pathlib import Path
import tempfile
import unittest

from bridge.domain import BridgeError
from bridge.engine import Engine
from bridge.systems import Systems


class SystemTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / 'data' / 'test-temp'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temp.name)
        self.engine = Engine(self.root)
        self.systems = Systems(self.root, self.engine)
        self.manifest = copy.deepcopy(self.systems.manifest)

    def tearDown(self):
        self.engine.shutdown(); self.temp.cleanup()

    def configure(self):
        folder = self.root / 'drive'; folder.mkdir(exist_ok=True)
        exe = self.root / 'program.exe'; exe.write_bytes(b'not executed')
        self.systems.configure({'alphaxiv_key':'fixture-alpha-key', 'zotero_key':'fixture-zotero-key', 'zotero_user_id':'123',
            'zotero_exe':str(exe), 'openresearch_exe':str(exe), 'linked_pdf_dir':str(folder),
            'acknowledgements':{'drive_signed_in':True,'zotero_sync_enabled':True,'orx_agent_ready':True}})

    def test_import_is_idempotent_and_preserves_existing_credentials_and_schedule(self):
        self.engine.config.values.update(auto_sync=True, sync_interval_seconds=300)
        self.engine.config._secrets['zotero_key']='existing-fixture-key'
        first = self.systems.install(self.manifest)
        again = self.systems.install(self.manifest)
        self.assertEqual(first['system'],again['system'])
        self.assertTrue(self.engine.config.values['auto_sync'])
        self.assertEqual(self.engine.config.secret('zotero_key'),'existing-fixture-key')
        self.assertEqual(self.engine.config.values['sync_interval_seconds'],300)

    def test_unreviewed_template_cannot_import_commands_secrets_or_urls(self):
        for field,value in [('command','malicious'),('zotero_user_id','999'),('defaults',{'auto_sync':True}),('version','99.0')]:
            altered=copy.deepcopy(self.manifest);altered[field]=value
            with self.assertRaises(BridgeError):self.systems.install(altered)
        self.assertFalse(self.systems.public()['installed'])

    def test_complete_setup_requires_api_checks_before_enabling(self):
        self.systems.install(self.manifest);self.configure()
        self.assertFalse(self.systems.public()['ready'])
        with self.assertRaises(BridgeError):self.systems.enable()
        self.engine.store.meta('checks',{'alpha':{'ok':True},'zotero_web':{'ok':True}})
        self.assertTrue(self.systems.public()['ready'])
        self.systems.enable()
        self.assertTrue(self.engine.config.values['auto_sync'])
        self.assertEqual(self.engine.config.values['sync_interval_seconds'],86400)
        self.assertEqual(self.engine.config.values['pdf_storage'],'linked_folder')
        self.assertFalse(self.engine.config.values['upload_pdf'])

    def test_setup_invalidates_checks_and_does_not_export_keys(self):
        self.systems.install(self.manifest);self.configure()
        self.engine.store.meta('checks',{'alpha':{'ok':True},'zotero_web':{'ok':True}})
        self.engine.save({'zotero_key':'changed-fixture-key'})
        self.assertFalse(self.systems.public()['ready'])
        text=json.dumps(self.systems.public())
        self.assertNotIn('fixture-alpha-key',text);self.assertNotIn('changed-fixture-key',text)
        self.assertNotIn(str(self.root),json.dumps(self.manifest))

    def test_drive_login_is_acknowledged_and_not_claimed_verified(self):
        self.systems.install(self.manifest);self.configure()
        self.systems.configure({'acknowledgements':{'drive_signed_in':False}})
        requirement=next(r for r in self.systems.public()['requirements'] if r['id']=='drive')
        self.assertFalse(requirement['ok']);self.assertIn('用户确认',requirement['label'])

    def test_template_never_claims_automatic_openresearch_handoff(self):
        orx=next(f for f in self.manifest['flows'] if f['target']=='openresearch')
        self.assertEqual(orx['mode'],'manual')
        self.assertEqual(self.systems.public()['diy_status'],'unfinished')

    def test_missing_local_files_and_unknown_configuration_block_setup(self):
        self.systems.install(self.manifest)
        with self.assertRaises(BridgeError):self.systems.configure({'openresearch_exe':str(self.root/'missing.exe')})
        with self.assertRaises(BridgeError):self.systems.configure({'auto_sync':True})
        self.assertFalse(self.systems.public()['ready'])
