"""Build the per-user Windows installer using Inno Setup 6.7+."""
import argparse, hashlib, pathlib, subprocess

PROJECT = pathlib.Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--iscc', required=True, help='Path to Inno Setup ISCC.exe')
    parser.add_argument('--release', required=True, help='Built MusicLibrary-Windows folder')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    release = pathlib.Path(args.release).resolve()
    output = pathlib.Path(args.output).resolve()
    if not (release / 'MusicLibrary.exe').is_file():
        raise FileNotFoundError('Build the Windows release first')
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(pathlib.Path(args.iscc).resolve()), '/Qp', '/DReleaseDir=' + str(release),
                    '/DOutputDir=' + str(output), str(PROJECT / 'installer' / 'MusicLibrary.iss')], check=True)
    files = sorted(output.glob('MusicLibrary-Setup-*.exe'))
    if len(files) != 1:
        raise RuntimeError('Expected one installer in a fresh output directory')
    installer = files[0]
    sums = output / 'SHA256SUMS.txt'
    entries = sums.read_text(encoding='ascii').splitlines() if sums.exists() else []
    entries = [line for line in entries if not line.endswith('  ' + installer.name)]
    entries.append(hashlib.sha256(installer.read_bytes()).hexdigest() + '  ' + installer.name)
    sums.write_text('\n'.join(entries) + '\n', encoding='ascii')
    print(installer)

if __name__ == '__main__':
    main()
