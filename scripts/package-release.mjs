import { readdir, readFile, writeFile, mkdir, copyFile, lstat } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
const root = fileURLToPath(new URL('../', import.meta.url));
const { version } = JSON.parse(await readFile(join(root, 'package.json'), 'utf8'));
const policy = JSON.parse(await readFile(join(root, 'LICENSING.json'), 'utf8'));
if (policy.policyId !== 'LicenseRef-Prototype-Plan-Personal-Noncommercial-1.1') throw Error('Unexpected release license');
if (policy.scope !== 'all-owner-controlled-material-in-official-distribution' || !policy.preservesPriorGrants || !policy.preservesThirdPartyLicenses) throw Error('Incomplete release licensing scope');
const output = join(root, 'artifacts/releases', `v${version}`), folder = join(output, 'research-nexus');
await mkdir(join(root, 'artifacts/releases'), { recursive: true });
await mkdir(output); // Refuse to overwrite a previously built release.
await mkdir(folder);
const hashes = [];
const hash = data => createHash('sha256').update(data).digest('hex');
const deny = /^(?:\.git|node_modules|data|vendor|artifacts|\.venv|__pycache__|runtime\.local\.json|NativeDockHost\.exe|\.env(?:\..*)?)$/i;
async function copy(relative) {
  const path = join(root, relative), info = await lstat(path);
  if (info.isSymbolicLink()) throw Error('Symlinks are not release inputs: ' + relative);
  if (info.isDirectory()) {
    await mkdir(join(folder, relative), { recursive: true });
    for (const name of (await readdir(path)).sort()) {
      if (deny.test(name) || /(?:\.py[co]|\.log|\.sqlite\d*(?:-wal|-shm)?|\.db|\.dpapi\.json|\.mp4|\.lnk|\.exe)$/i.test(name)) continue;
      await copy(join(relative, name));
    }
  } else if (info.isFile()) {
    await copyFile(path, join(folder, relative));
    hashes.push({ path: relative.replaceAll('\\', '/'), sha256: hash(await readFile(path)), bytes: info.size });
  }
}
for (const path of ['desktop', 'web', 'bridge', 'scripts', 'system-templates', 'docs', 'tests', 'LICENSES',
  'package.json', 'package-lock.json', 'requirements.txt', 'README.md', 'README.zh-CN.md', 'INSTALL.md',
  'LICENSE', 'LICENSING.json', 'LICENSE_HISTORY.md', 'COMMERCIAL_LICENSE.md', 'CONTRIBUTOR_AGREEMENT.md',
  'CONTRIBUTING.md', 'OWNERSHIP.md', 'THIRD_PARTY_NOTICES.md', 'SECURITY.md', 'AGENTS.md', '.gitignore',
  'Start Research Nexus.cmd', 'Start Research Nexus.vbs', 'Start System Templates.vbs', 'Start System Designer.vbs']) await copy(path);
const sourceCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8', windowsHide: true }).trim();
await writeFile(join(folder, 'RELEASE-MANIFEST.json'), JSON.stringify({ project: 'research-nexus', version,
  sourceCommit, distribution: 'windows-x64-source-kit', policyId: policy.policyId, licenseScope: policy.scope,
  dependencyBinariesBundled: false, files: hashes }, null, 2) + '\n');
const name = `research-nexus-v${version}-windows-source.zip`, zip = join(output, name);
execFileSync('powershell.exe', ['-NoProfile', '-Command', 'Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::CreateFromDirectory($env:RN_PACKAGE_DIRECTORY,$env:RN_ARCHIVE_PATH,[System.IO.Compression.CompressionLevel]::Optimal,$true)'],
  { windowsHide: true, stdio: 'inherit', env: { ...process.env, RN_PACKAGE_DIRECTORY: folder, RN_ARCHIVE_PATH: zip } });
const template = 'literature-workspace.rn-system.json';
await copyFile(join(root, 'system-templates', template), join(output, template));
const lines = [];
for (const file of [name, template]) lines.push(`${hash(await readFile(join(output, file)))}  ${file}`);
await writeFile(join(output, 'SHA256SUMS.txt'), lines.join('\n') + '\n');
console.log(JSON.stringify({ zip, sourceCommit, files: hashes.length, sha256: lines[0].split(' ')[0] }));
