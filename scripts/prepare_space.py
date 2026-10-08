"""Create a deployment folder containing only code and authored fictional demo data."""
import shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def prepare(destination):
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    for name in ('app.py','requirements.txt','packages.txt','pyproject.toml'):
        shutil.copyfile(ROOT/name,destination/name)
    for name in ('approval','demo'):
        shutil.copytree(ROOT/name,destination/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.sqlite*'))
    shutil.copyfile(ROOT/'docs/SPACE_README.md',destination/'README.md')
    (destination/'.gitignore').write_text('.env\n*.sqlite*\n__pycache__/\noutput/\n')
    return destination

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('destination',type=Path);args=p.parse_args()
    print(prepare(args.destination))
