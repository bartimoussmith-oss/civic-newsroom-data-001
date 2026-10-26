"""Lossless direct-text exports of the already published public representation collection."""
import csv
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

REPO='bartimoussmith-oss/civic-newsroom-data-001'
REF=re.compile(r'\b(ordinance|resolution|contract|PUDC)\s*(?:no\.?\s*|#\s*|-)?(\d[A-Za-z0-9]*(?:[-.]\d[A-Za-z0-9]*)*)\b',re.I)

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def local(root,relative):
    p=(root/relative).resolve()
    if root not in p.parents or not p.is_file():raise ValueError('Invalid source path')
    return p

def put_line(stream,value):
    stream.write((json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8'))

def compressed(path):
    return gzip.GzipFile(filename=str(path),mode='wb',mtime=0)

def export(repo,out):
    repo=Path(repo).resolve();out=Path(out)
    pointer=json.loads((repo/'published.json').read_text(encoding='utf-8'))
    if pointer['schema']!='civic-data-publication-v1' or not re.fullmatch('build-[0-9]+',pointer['dataset_version']):raise ValueError('Invalid public collection pointer')
    source=(repo/'datasets'/pointer['dataset_version']).resolve()
    raw=local(source,'collection.json').read_bytes()
    if sha256(raw).hexdigest()!=pointer['manifest_sha256']:raise ValueError('Manifest hash mismatch')
    manifest=json.loads(raw)
    if out.exists():raise ValueError('Refusing to overwrite export version')
    (out/'records').mkdir(parents=True);(out/'metadata').mkdir();(out/'jsonl').mkdir();(out/'years').mkdir()
    years={};count=0;edges=0;batch=[];batch_number=0;seen=set()
    def flush():
        nonlocal batch_number
        if not batch:return
        batch_number+=1
        with compressed(out/'jsonl'/('records-'+str(batch_number).zfill(4)+'.jsonl.gz')) as stream:
            for item in batch:put_line(stream,item)
        batch.clear()
    objects=compressed(out/'objects.jsonl.gz');mentions=compressed(out/'identifier-mentions.jsonl.gz');meta=compressed(out/'metadata.jsonl.gz')
    with (out/'metadata.csv').open('w',encoding='utf-8',newline='') as csvfile:
        writer=csv.writer(csvfile);writer.writerow(['record_id','title','year_path_label','representation_sha256','bytes','text_path','original_binary_identity'])
        try:
            for catalog in manifest['catalogs']:
                raw=local(source,catalog['path']).read_bytes()
                if sha256(raw).hexdigest()!=catalog['sha256'] or len(raw)!=catalog['bytes']:raise ValueError('Catalog integrity failure')
                for record in json.loads(raw):
                    rid=record['record_id'];path=record['source']['mirror_path']
                    if not re.fullmatch('[a-f0-9]{64}',rid) or rid in seen:raise ValueError('Invalid/duplicate record ID')
                    seen.add(rid)
                    if not path.startswith(('documents/','meetings/')):raise ValueError('Not an approved mirror record path')
                    parts=[]
                    for sequence,p in enumerate(record['representation']['parts']):
                        b=local(source,p['path']).read_bytes()
                        if p['sequence']!=sequence or len(b)!=p['bytes'] or sha256(b).hexdigest()!=p['sha256']:raise ValueError('Blob mismatch')
                        parts.append(b)
                    raw=b''.join(parts)
                    if len(raw)!=record['representation']['bytes'] or sha256(raw).hexdigest()!=record['representation']['sha256']:raise ValueError('Complete record mismatch')
                    text=raw.decode('utf-8');text_path='records/'+rid+'.md'
                    (out/text_path).write_bytes(raw)
                    date=re.search(r'/(\d{4})/',path);year=date.group(1) if date else 'unknown'
                    metadata={'schema':'public-record-export-v1','record_id':rid,'title':record['title'],'text_path':text_path,'representation_sha256':record['representation']['sha256'],'bytes':len(raw),'year_path_label':year,'date_review':'unverified_path_label','source':record['source'],'source_family':'unresolved','representation_kind':'generated_public_markdown','original_binary_copied':False,'internal_research_imported':False}
                    dump(out/'metadata'/(rid+'.json'),metadata);put_line(meta,metadata);put_line(objects,{'id':rid,'type':'document_representation','version':metadata['representation_sha256'],'metadata_path':'metadata/'+rid+'.json'})
                    writer.writerow([rid,record['title'],year,metadata['representation_sha256'],len(raw),text_path,'not_established'])
                    batch.append({'record_id':rid,'metadata':metadata,'text':text})
                    if len(batch)>=128:flush()
                    years.setdefault(year,[]).append((record['title'],rid))
                    for match in REF.finditer(text):
                        namespace=path.split('/')[2] if len(path.split('/'))>2 else 'unresolved'
                        put_line(mentions,{'schema':'literal-reference-edge-v1','record_id':rid,'record_version':metadata['representation_sha256'],'predicate':'mentions_identifier','identifier_type':match.group(1).lower(),'identifier':match.group(2),'namespace_hint':namespace,'span':{'start':match.start(),'end':match.end(),'unit':'unicode_code_points','text':match.group(0)},'review':'unreviewed_literal_match','limitations':'Not a verified ordinance/action/entity relationship; resolve jurisdiction, dates and identifier namespace before linking.'})
                        edges+=1
                    count+=1
            flush()
        finally:
            objects.close();mentions.close();meta.close()
    if count!=manifest['records']:raise ValueError('Export lost records')
    index=['# Cheyenne public record text exports','','Direct copies of generated public representations, not internal research. Full text is stored here; upstream links are provenance only. Original PDFs and complete historical coverage are not established.','','## Browse by year (path labels, not verified event dates)']
    for year,rows in sorted(years.items()):
        index.append('- ['+year+'](years/'+year+'.md): '+str(len(rows))+' representations')
        page=['# '+year+' public representations','','Year is a path label. Review original records and dates.','']
        for title,rid in rows:page.append('- ['+title.replace('[','(').replace(']',')').replace('\n',' ')+'](../records/'+rid+'.md) · [metadata](../metadata/'+rid+'.json)')
        (out/'years'/(year+'.md')).write_text('\n'.join(page)+'\n',encoding='utf-8')
    (out/'index.md').write_text('\n'.join(index)+'\n',encoding='utf-8')
    summary={'schema':'public-ai-archive-v1','records':count,'full_text_jsonl_batches':batch_number,'identifier_reference_edges':edges,'source_dataset_revision':pointer['dataset_revision'],'source_manifest_sha256':pointer['manifest_sha256'],'text_format':'UTF-8 Markdown, exact representation bytes','jsonl_format':'gzip-compressed JSON Lines; full text plus metadata','graph_status':'document objects and unreviewed literal identifier mentions only','original_binary_copies_present':False,'full_historical_coverage':False,'internal_research_imported':False,'source_policy':'Only already published documents/ and meetings/ generated representations. No repository-root research, advocacy drafts, casework, private folders or media commentary is imported. Public testimony inside official records is retained.'}
    dump(out/'collection.json',summary)
    (out/'llms.txt').write_text('# Cheyenne public record export\n\nRead index.md and collection.json. Full per-record text is in records/*.md with metadata/*.json. Full-text JSONL batches are in jsonl/. metadata.jsonl.gz and metadata.csv provide catalogs. objects.jsonl.gz and identifier-mentions.jsonl.gz contain explicitly limited graph exports. Do not treat machine OCR, caption attribution, path dates or literal matches as independently verified facts. No JavaScript, authentication, or reassembly is required for the Markdown records.\n',encoding='utf-8')
    files=list(out.rglob('*'))
    if any(p.stat().st_size>45*1024*1024 for p in files if p.is_file()):raise ValueError('Export file exceeds budget')
    existing=sum(p.stat().st_size for p in (repo/'datasets').rglob('*') if p.is_file())
    exports=sum(p.stat().st_size for p in (repo/'ai-archives').rglob('*') if p.is_file())
    if existing+exports>512*1024*1024:raise ValueError('Repository export budget reached; publish in another approved data repo')
    return summary

if __name__=='__main__':
    if os.environ.get('GITHUB_REPOSITORY')!=REPO:raise ValueError('Unexpected destination')
    repo=Path.cwd();pointer=json.loads((repo/'published.json').read_text())
    exporter_hash=sha256(Path(__file__).read_bytes()).hexdigest()
    version=sha256((pointer['dataset_revision']+exporter_hash).encode()).hexdigest()[:20]
    out=repo/'ai-archives'/version
    summary=export(repo,out)
    subprocess.run(['git','config','user.name','github-actions[bot]'],check=True)
    subprocess.run(['git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com'],check=True)
    subprocess.run(['git','add',str(out.relative_to(repo))],check=True)
    subprocess.run(['git','commit','-m','data: direct public-record exports '+version],check=True)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    base='https://raw.githubusercontent.com/'+REPO+'/'+revision+'/ai-archives/'+version+'/'
    descriptor={'schema':'public-ai-archive-publication-v1','export_revision':revision,'export_version':version,'base_url':base,'index_url':base+'index.md','collection_url':base+'collection.json','collection_sha256':sha256((out/'collection.json').read_bytes()).hexdigest(),'records':summary['records'],'source_dataset_revision':summary['source_dataset_revision'],'full_historical_coverage':False}
    dump(repo/'ai-archive.json',descriptor)
    subprocess.run(['git','add','ai-archive.json'],check=True)
    subprocess.run(['git','commit','-m','publish: pin direct AI archive '+revision],check=True)
    subprocess.run(['git','push','origin','HEAD:main'],check=True)
    print(json.dumps(descriptor,indent=2))
