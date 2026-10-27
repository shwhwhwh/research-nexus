"""Locally reviewed component recipes. Blueprints cannot supply install commands."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import requests

from .domain import BridgeError
from .storage import Config

CATALOG = {
    'folder': {'name': 'RN 本地数据目录', 'kind': 'folder'},
    'website': {'name': '网页', 'kind': 'website'},
    'http-api': {'name': 'HTTP API', 'kind': 'website'},
    'alphaxiv': {'name': 'alphaXiv', 'kind': 'website', 'builtin': 'alpha', 'url': 'https://www.alphaxiv.org/'},
    'zotero': {'name': 'Zotero', 'kind': 'app', 'builtin': 'zotero', 'package': 'DigitalScholar.Zotero', 'config': 'zotero_exe'},
    'openresearch': {'name': 'OpenResearch', 'kind': 'app', 'builtin': 'openresearch', 'config': 'openresearch_exe', 'setup_url': 'https://github.com/alphaXiv/OpenResearch/releases'},
    'google-drive': {'name': 'Google Drive', 'kind': 'app', 'package': 'Google.GoogleDrive', 'paths': [r'Google\Drive File Stream\launch.bat']},
    'obsidian': {'name': 'Obsidian', 'kind': 'app', 'package': 'Obsidian.Obsidian', 'paths': [r'Programs\Obsidian\Obsidian.exe', r'Obsidian\Obsidian.exe']},
    'python': {'name': 'Python', 'kind': 'app', 'package': 'Python.Python.3.13', 'command': 'python'},
    'node': {'name': 'Node.js LTS', 'kind': 'app', 'package': 'OpenJS.NodeJS.LTS', 'command': 'node'},
    'git': {'name': 'Git', 'kind': 'app', 'package': 'Git.Git', 'command': 'git'},
}


class Components:
    def __init__(self, root, designer):
        self.root, self.designer = Path(root), designer
        self.cancelled = set()
        self.cache = self.root / 'data' / 'builder' / 'components'
        self.cache.mkdir(parents=True, exist_ok=True)

    def detect(self, recipe):
        item = CATALOG[recipe]
        if recipe in ('folder', 'website', 'http-api', 'alphaxiv'):
            return {'ready': True, 'method': 'builtin'}
        cfg = self.designer.engine.config.snapshot() if self.designer.engine else {}
        candidates = [cfg.get(item.get('config', ''), '')]
        if recipe == 'python': candidates.append(sys.executable)
        if item.get('command'): candidates.append(shutil.which(item['command']) or '')
        for base in (os.environ.get('LOCALAPPDATA', ''), os.environ.get('ProgramFiles', ''), os.environ.get('ProgramFiles(x86)', '')):
            if base:
                candidates.extend(str(p) for relative in item.get('paths', []) for p in Path(base).glob(relative.replace('\\', '/')))
        if recipe == 'google-drive':
            for base in (os.environ.get('ProgramFiles', ''), os.environ.get('ProgramFiles(x86)', '')):
                if base: candidates.extend(str(p) for p in (Path(base) / 'Google/Drive File Stream').glob('*/GoogleDriveFS.exe'))
        if recipe == 'zotero': candidates.append(str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Zotero/zotero.exe'))
        if recipe == 'openresearch': candidates.append(str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/OpenResearch/orx.exe'))
        for value in candidates:
            if value and Path(value).is_file() and Path(value).suffix.lower() == '.exe':
                return {'ready': True, 'method': 'existing', 'executable': value}
        return {'ready': False, 'method': 'winget' if item.get('package') else 'manual', 'setup_url': item.get('setup_url', '')}

    def command(self, args, job_id):
        if job_id in self.cancelled: raise BridgeError('构建已停止。')
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        key = 'system-' + job_id
        with self.designer.lock: self.designer.processes[key] = process
        try:
            output, _ = process.communicate(timeout=900)
        except subprocess.TimeoutExpired:
            self.designer._terminate(process)
            raise BridgeError('组件准备超过 15 分钟；可在系统构建窗口继续重试。') from None
        finally:
            with self.designer.lock: self.designer.processes.pop(key, None)
        if process.returncode:
            raise BridgeError('组件管理器未完成：' + self.designer._redact(output[-1500:]))
        return output

    def prepare(self, component, install, job_id, log):
        if job_id in self.cancelled: raise BridgeError('构建已停止。')
        recipe = component['recipe']; item = CATALOG[recipe]; detected = self.detect(recipe)
        if detected['ready']:
            if recipe == 'folder':
                target = self.designer.base / 'outputs' / component.get('runtime_id', component['id'])
                target.mkdir(parents=True, exist_ok=True)
            if item.get('config') and self.designer.engine:
                self.designer.engine.save({item['config']: detected['executable']})
            log(item['name'] + '：复用本机组件。')
            return {**detected, 'status': 'ready'}
        if recipe == 'openresearch':
            return self.openresearch(install, job_id, log)
        if not item.get('package'):
            return {**detected, 'status': 'needs_setup', 'requirement': '安装 ' + item['name'] + ' 并在连接设置中选择本机程序。'}
        winget = shutil.which('winget')
        if not winget:
            return {'status': 'needs_setup', 'requirement': '请安装 Windows App Installer / WinGet，再继续。'}
        package = item['package']; folder = self.cache / package; folder.mkdir(exist_ok=True)
        receipt_file = folder / 'download.json'
        receipt = json.loads(receipt_file.read_text(encoding='utf-8')) if receipt_file.exists() else {}
        valid = receipt.get('version') and receipt.get('files') and all((folder / name).is_file() and hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest for name, digest in receipt['files'].items())
        if not valid:
            log('下载组件：' + item['name'])
            self.command([winget, 'download', '--id', package, '--exact', '--source', 'winget', '--download-directory', str(folder),
                '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity'], job_id)
            files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.exe', '.msi', '.msix', '.zip', '.yaml')}
            if not files: raise BridgeError('下载未产生可验证的安装资源。')
            versions = [m[1].strip(' \"\'') for p in folder.glob('*.yaml') for m in re.finditer(r'(?m)^PackageVersion:\s*(.+)$', p.read_text(encoding='utf-8-sig'))]
            if not versions: raise BridgeError('下载资源未包含组件版本，暂不继续安装。')
            receipt = {'package': package, 'files': files, 'version': versions[0]}
            Config._atomic(receipt_file, receipt)
        if not install:
            return {'status': 'needs_setup', 'downloaded': True, 'requirement': item['name'] + ' 已下载；勾选安装缺少组件后继续。'}
        log('安装组件：' + item['name'])
        # WinGet performs its own manifest/hash verification. No template-provided shell or installer arguments.
        if not re.fullmatch(r'[a-zA-Z0-9._+-]{1,80}', receipt.get('version', '')): raise BridgeError('组件版本无效，请重新下载。')
        self.command([winget, 'install', '--id', package, '--version', receipt['version'], '--exact', '--source', 'winget', '--no-upgrade', '--silent',
            '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity'], job_id)
        detected = self.detect(recipe)
        if not detected['ready']:
            return {'status': 'needs_setup', 'downloaded': True, 'requirement': item['name'] + ' 安装命令已结束；请在本机确认安装位置后继续。'}
        if item.get('config') and self.designer.engine:
            self.designer.engine.save({item['config']: detected['executable']})
        return {**detected, 'status': 'ready', 'downloaded': True}

    def openresearch(self, install, job_id, log):
        # The official CLI bundle contains `orx app`. RN supplies only a tiny
        # console-free launcher, so this managed installation needs no admin rights.
        from zipfile import ZipFile
        folder = self.cache / 'OpenResearch'; folder.mkdir(exist_ok=True)
        archive, receipt_file = folder / 'openresearch.zip', folder / 'download.json'
        receipt = json.loads(receipt_file.read_text()) if receipt_file.exists() else {}
        if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != receipt.get('sha256'):
            log('从官方 OpenResearch 发行页下载 Windows 组件并核对 SHA-256。')
            with requests.Session() as session:
                session.trust_env = False
                response = session.get('https://github.com/alphaXiv/OpenResearch/releases/latest', timeout=30)
                response.raise_for_status()
                tag = response.url.rsplit('/', 1)[-1]
                if not re.fullmatch(r'v[0-9][a-zA-Z0-9._-]{0,50}', tag): raise BridgeError('无法核对 OpenResearch 官方版本。')
                base = 'https://github.com/alphaXiv/OpenResearch/releases/download/' + tag + '/'
                asset = 'openresearch-cli-x86_64-pc-windows-msvc.zip'
                checks = session.get(base + asset + '.sha256', timeout=30); checks.raise_for_status()
                expected = checks.text.split()[0]
                if not re.fullmatch('[0-9a-fA-F]{64}', expected): raise BridgeError('官方发行包没有可用的 SHA-256 校验。')
                temporary = folder / 'download.part'; sha, size = hashlib.sha256(), 0
                with session.get(base + asset, stream=True, timeout=45) as download:
                    download.raise_for_status()
                    with temporary.open('wb') as output:
                        for chunk in download.iter_content(262144):
                            size += len(chunk)
                            if size > 150000000: raise BridgeError('OpenResearch 下载超出上限。')
                            if self.designer.stop_event.is_set() or job_id in self.cancelled: raise BridgeError('已停止下载。')
                            sha.update(chunk); output.write(chunk)
                if sha.hexdigest().lower() != expected.lower(): raise BridgeError('组件校验不一致，未执行。')
                temporary.replace(archive); Config._atomic(receipt_file, {'version': tag, 'sha256': sha.hexdigest()})
        if job_id in self.cancelled: raise BridgeError('构建已停止。')
        if not install: return {'status': 'needs_setup', 'downloaded': True, 'requirement': 'OpenResearch 已下载；勾选安装缺少组件后继续。'}
        with ZipFile(archive) as bundle:
            for name in ('orx.exe', 'LICENSE', 'README.md'):
                info = bundle.getinfo(name)
                if info.file_size > 200000000: raise BridgeError('组件展开大小超出上限。')
                (folder / name).write_bytes(bundle.read(info))
        compiler = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        if not compiler.is_file(): return {'status': 'needs_setup', 'requirement': '需要 Windows .NET Framework 编译器以准备 OpenResearch 启动器。'}
        source = folder / 'Launcher.cs'; launcher = folder / 'OpenResearch.exe'
        source.write_text('using System;using System.Diagnostics;using System.IO;class Launcher{static void Main(){Process.Start(new ProcessStartInfo(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"orx.exe"),"app"){UseShellExecute=false,CreateNoWindow=true});}}', encoding='utf-8')
        self.command([str(compiler), '/nologo', '/target:winexe', '/out:' + str(launcher), str(source)], job_id)
        if not launcher.is_file(): raise BridgeError('OpenResearch 启动器未生成。')
        if self.designer.engine: self.designer.engine.save({'openresearch_exe': str(launcher)})
        log('OpenResearch：已准备 RN 管理的本地组件。')
        return {'ready': True, 'method': 'managed-bundle', 'executable': str(launcher), 'status': 'ready', 'downloaded': True}
