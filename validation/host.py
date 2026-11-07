"""Verify sealed inputs, then run one owned hosted Docker lane."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
P=Path(__file__).resolve().parent

def verify():
 m=json.loads((P/'manifest.json').read_text())
 actual={str(x.relative_to(P))for x in P.rglob('*')if x.is_file()}
 assert actual==set(m['files'])|{'manifest.json'},'PAYLOAD_SCOPE'
 for n,h in m['files'].items():assert hashlib.sha256((P/n).read_bytes()).hexdigest()==h,('PAYLOAD_HASH',n)
 assert (P/'workflow.yml').read_bytes()==(P.parent/'.github/workflows/pymc8467.yml').read_bytes(),'WORKFLOW_DRIFT'
 tree=set(subprocess.check_output(['git','ls-tree','-r','--name-only','HEAD'],text=True).splitlines())
 assert tree=={'validation/'+n for n in m['files']}|{'validation/manifest.json','.github/workflows/pymc8467.yml'},'GIT_TREE_SCOPE'
 header=subprocess.check_output(['git','cat-file','-p','HEAD'],text=True).split('\n\n',1)[0]
 assert not [l for l in header.splitlines()if l.startswith('parent ')],'DIAGNOSTIC_PARENTLESS'
 return m
if sys.argv[1:]==['--verify-only']:
 m=verify();print(json.dumps({'state':'METADATA_ONLY_EXACT_PACKET','files':len(m['files'])}));sys.exit(0)
assert os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
assert os.environ.get('GITHUB_REPOSITORY')=='leninworld/pymc'
assert os.environ.get('GITHUB_RUN_ATTEMPT')=='1'
variant=os.environ['VARIANT'];mode=os.environ['FLOATX'];origin=int(os.environ['PACKET_ORIGIN']);lane_end=origin+2700
assert variant in ['baseline','candidate']and mode in ['float64','float32']
root=Path(os.environ['RUNNER_TEMP']).resolve();W=root/f'pymc8467-{variant}-{mode}';assert not W.exists();W.mkdir();E=W/'evidence';E.mkdir()
record={'state':'INCOMPLETE','variant':variant,'floatX':mode,'origin':origin};name=f'pymc8467-{os.environ["GITHUB_RUN_ID"]}-{variant}-{mode}';created=False

def run(label,args,cap=60):
 remaining=min(cap,lane_end-time.time()-90);assert remaining>0,'COMMON_DEADLINE'
 with (E/(label+'.stdout')).open('xb')as out,(E/(label+'.stderr')).open('xb')as err:r=subprocess.run(list(map(str,args)),stdout=out,stderr=err,timeout=remaining)
 assert r.returncode==0,(label,r.returncode)

def phase(label,cap):
 start=time.monotonic()
 with (E/(label+'-host.stdout')).open('xb')as out,(E/(label+'-host.stderr')).open('xb')as err:
  proc=subprocess.Popen(['docker','exec',name,'python3','/inputs/inside.py',label],stdout=out,stderr=err)
  try:
   while proc.poll()is None:
    assert time.monotonic()-start<cap and time.time()<lane_end-120,'PHASE_OR_COMMON_DEADLINE'
    assert os.statvfs(W).f_bavail*os.statvfs(W).f_frsize>=3*2**30,'DISK_FLOOR'
    with (E/'docker-samples.jsonl').open('a')as samples:
     samples.write(json.dumps({'at':time.time(),'stats':subprocess.check_output(['docker','stats','--no-stream','--format','{{json .}}',name],text=True,timeout=10).strip()})+'\n')
    time.sleep(5)
   assert proc.returncode==0,(label,proc.returncode)
  finally:
   if proc.poll()is None:
    proc.terminate()
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
try:
 m=verify();assert m['state']=='SEALED_FOR_ONE_RUN','EXECUTION_NOT_APPROVED';assert os.environ['GITHUB_REF']==m['ref'];assert lane_end-time.time()>=2100,'INSUFFICIENT_ORIGINAL_RUN_TIME'
 mem={l.split(':')[0]:int(l.split()[1])*1024 for l in Path('/proc/meminfo').read_text().splitlines()}
 assert mem['MemAvailable']>=10*2**30 and mem['MemTotal']>=15*2**30 and len(os.sched_getaffinity(0))>=4,'HOST_CAPACITY'
 assert os.statvfs(W).f_bavail*os.statvfs(W).f_frsize>=10*2**30,'INITIAL_DISK'
 record['admission']={'memory':mem,'cpu_affinity':sorted(os.sched_getaffinity(0)),'initial_free':os.statvfs(W).f_bavail*os.statvfs(W).f_frsize}
 run('image',['docker','pull','--platform','linux/amd64',m['image']],180)
 run('create',['docker','create','--name',name,'--platform','linux/amd64','--init','--user',f'{os.getuid()}:{os.getgid()}','--memory','12g','--memory-swap','12g','--pids-limit','1024','--cap-drop','ALL','--security-opt','no-new-privileges','--env','VARIANT='+variant,'--env','FLOATX='+mode,'--env','PACKET_ORIGIN='+str(origin),'--mount','type=bind,src='+str(P)+',dst=/inputs,readonly','--mount','type=bind,src='+str(W)+',dst=/work',m['image'],'sleep','infinity']);created=True
 run('start',['docker','start',name]);phase('prepare',1500)
 run('isolate',['docker','network','disconnect','bridge',name]);inspection=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]
 assert not inspection['NetworkSettings']['Networks'] and inspection['HostConfig']['Memory']==inspection['HostConfig']['MemorySwap']==12*2**30
 assert inspection['HostConfig']['NanoCpus']==0 and not inspection['HostConfig']['CpusetCpus'],'NO_CPU_THROTTLE'
 phase('test',2100);record['state']='COMPLETE'
except BaseException as error:record['error']=repr(error);raise
finally:
 if created:
  try:
   subprocess.run(['docker','stop','--time','10',name],check=True,capture_output=True,timeout=25)
   d=json.loads(subprocess.check_output(['docker','inspect',name],text=True,timeout=15))[0]['State'];record.update(container_stopped=not d['Running'],OOMKilled=d['OOMKilled'],container_state=d)
   if d['Running']or d['OOMKilled']:record['state']='INCOMPLETE'
  except BaseException as error:record['cleanup_error']=repr(error);record['state']='INCOMPLETE'
 record['elapsed']=time.time()-origin;(E/'host.json').write_text(json.dumps(record,indent=2)+'\n')
