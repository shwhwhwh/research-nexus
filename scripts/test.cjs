const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
let configured = {};
try { configured = JSON.parse(fs.readFileSync(path.join(root, 'runtime.local.json'), 'utf8')); } catch {}
const result = spawnSync(process.env.RESEARCH_NEXUS_PYTHON || process.env.RESEARCH_BRIDGE_PYTHON || configured.python || 'python',
  ['-m', 'unittest', 'discover', '-s', 'tests', '-v'], {cwd: root, stdio: 'inherit', windowsHide: true});
if (result.error) console.error(result.error.message);
process.exit(result.status ?? 1);
