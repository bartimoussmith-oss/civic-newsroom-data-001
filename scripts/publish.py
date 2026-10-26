"""Validate public normalized data and publish versioned files in this data repo only."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

REPO='bartimoussmith-oss/civic-newsroom-data-001'

def git(*args):
    return subprocess.check_output(['git',*args],text=True).strip()

def local(root,relative):
    if not isinstance(relative,str): raise ValueError('Invalid data path')
    candidate=root/relative
    if candidate.is_symlink(): raise ValueError('Symlink in dataset')
    path=candidate.resolve()
    if root not in path.parents or not path.is_file(): raise ValueError('Missing/escaping data path')
    return path

def validate(root):
    root=Path(root).resolve()
    manifest=json.loads((root/'collection.json').read_text(encoding='utf-8'))
    if manifest.get('schema')!='civic-data-collection-v1': raise ValueError('Unexpected schema')
    if manifest.get('records')!=6065 or manifest.get('input_representation_bytes')!=168959761:
        raise ValueError('Public input baseline changed; review before publication')
    count=0;total=0;seen=set()
    for c in manifest['catalogs']:
        raw=local(root,c['path']).read_bytes()
        if len(raw)!=c['bytes'] or sha256(raw).hexdigest()!=c['sha256']: raise ValueError('Catalog integrity failure')
        records=json.loads(raw)
        if len(records)!=c['records']: raise ValueError('Catalog count mismatch')
        for r in records:
            if r['record_id'] in seen: raise ValueError('Duplicate record identity')
            seen.add(r['record_id'])
            if not r['source']['mirror_path'].startswith(('documents/','meetings/')): raise ValueError('Unapproved record path')
            digest=sha256();length=0
            for sequence,p in enumerate(r['representation']['parts']):
                if p['sequence']!=sequence: raise ValueError('Part sequence mismatch')
                chunk=local(root,p['path']).read_bytes()
                if len(chunk)!=p['bytes'] or sha256(chunk).hexdigest()!=p['sha256']: raise ValueError('Blob integrity failure')
                digest.update(chunk);length+=len(chunk)
            if length!=r['representation']['bytes'] or digest.hexdigest()!=r['representation']['sha256']: raise ValueError('Record integrity failure')
            count+=1;total+=length
    if count!=manifest['records'] or total!=manifest['input_representation_bytes']: raise ValueError('Collection count/byte mismatch')
    for f in root.rglob('*'):
        if f.is_symlink(): raise ValueError('Dataset symlink')
        if f.is_file() and f.stat().st_size>45*1024*1024: raise ValueError('File exceeds publication budget')
    size=sum(f.stat().st_size for f in root.rglob('*') if f.is_file())
    if size>256*1024*1024: raise ValueError('Dataset requires more than one approved data host')
    return manifest,size

def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);a=p.parse_args()
    if os.environ.get('GITHUB_REPOSITORY')!=REPO: raise ValueError('Wrong destination repository')
    manifest,size=validate(a.dataset)
    run=os.environ['GITHUB_RUN_ID']
    if not re.fullmatch(r'[0-9]+',run): raise ValueError('Invalid run ID')
    version='build-'+run
    destination=Path('datasets')/version
    if destination.exists(): raise ValueError('Dataset version already exists; refusing overwrite')
    existing=sum(f.stat().st_size for f in Path('datasets').rglob('*') if f.is_file()) if Path('datasets').exists() else 0
    if existing+size>512*1024*1024: raise ValueError('Data repository budget reached; allocate another approved host')
    destination.parent.mkdir(exist_ok=True)
    shutil.copytree(a.dataset,destination)
    git('config','user.name','github-actions[bot]')
    git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    git('add',str(destination))
    git('commit','-m','data: verified public dataset '+version)
    revision=git('rev-parse','HEAD')
    base='https://raw.githubusercontent.com/'+REPO+'/'+revision+'/'+destination.as_posix()+'/'
    raw=(destination/'collection.json').read_bytes()
    pointer={'schema':'civic-data-publication-v1','dataset_revision':revision,'dataset_version':version,'manifest_url':base+'collection.json','manifest_sha256':sha256(raw).hexdigest(),'data_base_url':base,'records':manifest['records'],'input_representation_bytes':manifest['input_representation_bytes'],'published_dataset_bytes':size,'producer_revision':manifest['producer_revision'],'workflow_run':run,'record_status':'generated_public_representations_not_independently_verified','full_historical_coverage':False}
    Path('published.json').write_text(json.dumps(pointer,indent=2),encoding='utf-8')
    git('add','published.json')
    git('commit','-m','publish: pin collection pointer to '+revision)
    git('push','origin','HEAD:main')
    print(json.dumps(pointer,indent=2))

if __name__=='__main__': main()
