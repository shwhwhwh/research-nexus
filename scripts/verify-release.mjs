import { mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';
const { version } = JSON.parse(await readFile('package.json', 'utf8'));
const zip = resolve(process.argv[2] || `artifacts/releases/v${version}/research-nexus-v${version}-windows-source.zip`);
await mkdir('artifacts/release-tests', { recursive: true });
const target = await mkdtemp(resolve('artifacts/release-tests/clean-'));
execFileSync('powershell.exe', ['-NoProfile', '-Command', 'Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::ExtractToDirectory($env:RN_TEST_ZIP,$env:RN_TEST_ROOT)'],
  { windowsHide: true, env: { ...process.env, RN_TEST_ZIP: zip, RN_TEST_ROOT: target } });
const root = join(target, 'research-nexus'), manifest = JSON.parse(await readFile(join(root, 'RELEASE-MANIFEST.json'), 'utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
assert.equal(manifest.version, version);
for (const file of manifest.files) {
  assert(!/(?:^|\/)(?:data|node_modules|vendor|\.git|__pycache__)(?:\/|$)/.test(file.path));
  assert.equal(hash(await readFile(join(root, file.path))), file.sha256, file.path);
}
for (const file of ['LICENSE', 'LICENSING.json', 'LICENSE_HISTORY.md', 'COMMERCIAL_LICENSE.md', 'CONTRIBUTOR_AGREEMENT.md', 'INSTALL.md', 'LICENSES/research-nexus-legacy-MIT.txt'])
  assert.equal(hash(await readFile(join(root, file))), hash(await readFile(file)), file);
const top = await readdir(root); assert(!top.includes('data')); assert(!top.includes('node_modules'));
const run = (program, args) => execFileSync(program, args, { cwd: root, windowsHide: true, stdio: 'inherit', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
run(process.execPath, ['scripts/check-license-policy.mjs']);
for (const folder of ['desktop', 'web', 'scripts']) for (const file of await readdir(join(root, folder)))
  if (/\.(?:cjs|mjs|js)$/.test(file)) run(process.execPath, ['--check', join(folder, file)]);
run(process.execPath, ['--test', 'tests/desktop-lifecycle.test.cjs', 'tests/graph-layout.test.cjs']);
run(process.env.RESEARCH_NEXUS_PYTHON || 'python', ['-m', 'unittest', 'discover', '-s', 'tests', '-v']);
run('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'desktop/build-native-host.ps1']);
await writeFile('artifacts/release-verification.json', JSON.stringify({ version, zip, sha256: hash(await readFile(zip)),
  sourceCommit: manifest.sourceCommit, cleanExtractionPassed: true, filesVerified: manifest.files.length,
  policyAndHistoricalNoticesPreserved: true, syntaxAndUnitTestsPassed: true, nativeHostCompiled: true, modelCalls: 0, testRoot: target }, null, 2));
console.log('Passed: clean source ZIP, all file hashes, rights/history, syntax, Python/Node tests and native-host build.');
