"""Create public source and Windows portable ZIPs without private test data.

Run with the isolated build environment described in README.md.
"""
import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from semlegend import __version__


def public_files():
    files = [p for pattern in ('*.py', '*.bat', '*.md', 'requirements*.txt', 'LICENSE', '.gitignore', '.gitattributes')
             for p in ROOT.glob(pattern)]
    for folder in ('semlegend', 'tests', 'tools', '.github', 'licenses'):
        files.extend(p for p in (ROOT / folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    files.extend([ROOT / 'example' / 'README.md', ROOT / 'example' / 'SAMPLES.json'])
    records = json.loads((ROOT / 'example' / 'SAMPLES.json').read_text(encoding='utf-8'))
    for record in records:
        if record.get('redistributable'):
            p = ROOT / 'example' / record['file']
            assert hashlib.sha256(p.read_bytes()).hexdigest() == record['sha256'], p
            files.append(p)
    return sorted(set(files))


def zip_tree(folder, output):
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for p in sorted(folder.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
                archive.write(p, str(Path(folder.name) / p.relative_to(folder)))


def dependency_licenses(destination):
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('Pillow', 'numpy', 'tkinterdnd2', 'pyinstaller'):
        dist = importlib.metadata.distribution(name)
        for f in dist.files or []:
            if any(word in f.name.lower() for word in ('license', 'copying', 'notice')):
                source = Path(dist.locate_file(f))
                if source.is_file():
                    target = destination / name / str(f).replace('/', '__').replace('\\', '__')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    for p in Path(sys.base_prefix).glob('LICENSE*'):
        if p.is_file():
            shutil.copy2(p, destination / ('Python-' + p.name))
    for base in (Path(sys.base_prefix) / 'tcl', Path(sys.base_prefix) / 'Library' / 'lib'):
        for p in base.glob('*/license*'):
            if p.is_file() and p.parent.name.startswith(('tk', 'tcl')):
                shutil.copy2(p, destination / (p.parent.name + '-' + p.name))
    shutil.copytree(ROOT / 'licenses', destination / 'runtime', dirs_exist_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-only', action='store_true')
    args = parser.parse_args()
    files = public_files()
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    source_zip = output / f'SEM-Legend-{__version__}-source.zip'
    prefix = Path(f'SEM-Legend-{__version__}')
    with zipfile.ZipFile(source_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for p in files:
            archive.write(p, str(prefix / p.relative_to(ROOT)))
    if not args.source_only:
        extra_binaries = []
        # A venv based on Conda does not expose Library/bin to the bundler.
        for name in ('ffi.dll', 'tcl86t.dll', 'tk86t.dll'):
            dll = Path(sys.base_prefix) / 'Library' / 'bin' / name
            if dll.is_file():
                extra_binaries.extend(['--add-binary', str(dll) + ';.'])
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                        '--onedir', '--windowed', '--name', 'SEM-Legend',
                        '--distpath', str(ROOT / '.build' / 'portable'),
                        '--workpath', str(ROOT / '.build' / 'pyinstaller'),
                        '--specpath', str(ROOT / '.build'),
                        '--collect-all', 'tkinterdnd2', '--add-data',
                        str(ROOT / 'windows_ocr.ps1') + ';.', *extra_binaries, str(ROOT / 'app.py')],
                       cwd=ROOT, check=True)
        portable = ROOT / '.build' / 'portable' / 'SEM-Legend'
        for p in files:
            if p.relative_to(ROOT).parts[0] == 'example' or p.name in ('README.md', 'LICENSE', 'CHANGELOG.md'):
                target = portable / p.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target)
        dependency_licenses(portable / 'THIRD_PARTY_LICENSES')
        subprocess.run([str(portable / 'SEM-Legend.exe'), '--self-test',
                        str(ROOT / '.build' / 'portable-selftest.json')], check=True, timeout=120)
        report = json.loads((ROOT / '.build' / 'portable-selftest.json').read_text(encoding='utf-8'))
        assert report['passed']
        (portable / 'BUILD-INFO.txt').write_text(
            f'SEM Legend {__version__}\nWindows x64 portable\nPython {sys.version}\n' +
            '\n'.join(f'{name}=={importlib.metadata.version(name)}'
                      for name in ('Pillow', 'numpy', 'tkinterdnd2', 'pyinstaller')) + '\n', encoding='utf-8')
        zip_tree(portable, output / f'SEM-Legend-{__version__}-windows-x64.zip')
    archives = sorted(output.glob(f'SEM-Legend-{__version__}-*.zip'))
    (output / 'SHA256SUMS.txt').write_text(''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in archives), encoding='utf-8')
    for p in archives:
        print(f'{p.name}: {p.stat().st_size / 1024 / 1024:.2f} MiB')


if __name__ == '__main__':
    main()
