"""Use upstream commands in an owned Docker filesystem; no project code on Mac."""
from pathlib import Path
import subprocess,os,sys,json,time,hashlib,resource,tarfile,io
P=Path('/inputs');W=Path('/work');E=W/'evidence';E.mkdir(exist_ok=True)
M=json.loads((P/'manifest.json').read_text());variant=os.environ['VARIANT'];mode=os.environ['FLOATX'];origin=int(os.environ['PACKET_ORIGIN']);lane_end=origin+2700
state_path=E/'state.json';state=json.loads(state_path.read_text())if state_path.exists()else {'state':'INCOMPLETE','variant':variant,'floatX':mode,'origin':origin,'commands':[]}
S=W/'source';V=W/'venv';PY=V/'bin/python';os.environ['PATH']=str(V/'bin')+os.pathsep+os.environ['PATH'];FILES=['pymc/data.py','pymc/model/core.py','pymc/pytensorf.py','tests/test_data.py','tests/test_pytensorf.py']
task_home=W/'home';task_home.mkdir(exist_ok=True)
# This is the controlled container user's actual home, never the Mac's HOME.
os.environ['HOME']=str(task_home)
os.environ['PYTENSOR_FLAGS']='base_compiledir=/work/pytensor-cache'
os.environ.update(UV_CACHE_DIR='/work/uv-cache',PRE_COMMIT_HOME='/work/precommit',VIRTUALENV_OVERRIDE_APP_DATA='/work/virtualenv',XDG_CACHE_HOME='/work/xdg-cache',UV_PYTHON_DOWNLOADS='never',UV_HTTP_RETRIES='0',UV_HTTP_TIMEOUT='20',PIP_INDEX_URL='https://pypi.org/simple',GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_SYSTEM='/dev/null',GIT_CONFIG_NOSYSTEM='1',NUMBA_CACHE_DIR='/work/numba-cache')
def save():state_path.write_text(json.dumps(state,indent=2)+'\n')
def run(label,args,cap=600,allowed=(0,),cwd=None):
 remaining=min(cap,lane_end-time.time()-120);assert remaining>0,'COMMON_DEADLINE'
 row={'label':label,'argv':list(map(str,args)),'cap':remaining};start=time.monotonic()
 try:
  with (E/(label+'.stdout')).open('xb')as out,(E/(label+'.stderr')).open('xb')as err:
   result=subprocess.run(list(map(str,args)),cwd=cwd or W,stdout=out,stderr=err,timeout=remaining)
  row['exit']=result.returncode;assert result.returncode in allowed,(label,result.returncode)
 finally:
  row['seconds']=time.monotonic()-start;row['cumulative_child_maxrss_KiB']=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss;state['commands'].append(row);save()
def unpack(archive,root):
 target=root/'source';assert not target.exists(),'EXTRACTION_PATH_ALREADY_EXISTS'
 root.mkdir(exist_ok=True)
 with tarfile.open(archive)as t:t.extractall(root,filter='data')
 assert target.is_dir();return target
def fingerprint():return {f:hashlib.sha256((S/f).read_bytes()).hexdigest()for f in FILES}
try:
 phase=sys.argv[1]
 if phase=='prepare':
  # Same real extraction routine and distinct roots before package downloads.
  for name in ['baseline','candidate']:
   root=W/('fixture-'+name);root.mkdir();archive=root/'tiny.tar.gz'
   with tarfile.open(archive,'w:gz')as t:
    payload=b'fixture\n';i=tarfile.TarInfo('source/file.txt');i.size=len(payload);t.addfile(i,io.BytesIO(payload))
   assert (unpack(archive,root)/'file.txt').read_bytes()==b'fixture\n'
  run('comparison-fixture',['python3',P/'compare.py','--fixture'],30)
  unpack(P/(variant+'.tar.gz'),W);state['source_fingerprints_before']=fingerprint();assert state['source_fingerprints_before']==M['source_fingerprints'][variant];save()
  assert sys.version_info[:3]==(3,12,13),'EXPECTED_IMAGE_PYTHON'
  run('toolchain',['bash','-e','-c','python3 --version; uv --version; git --version; g++ --version || true'],30)
  run('git-init',['git','init','--initial-branch','fix-data-dtype-issue-7277',S],30)
  run('git-add',['git','add','--all'],30,cwd=S)
  run('venv',['uv','venv','--python','/usr/local/bin/python3',V],60)
  run('dependencies',['uv','pip','install','--python',PY,'--only-binary',':all:','--require-hashes','--default-index','https://pypi.org/simple','-r',P/'requirements.txt'],600)
  run('editable',['uv','pip','install','--python',PY,'--no-deps','--no-build-isolation','-e',S],180)
  run('versions',[PY,'-c','import sys,platform,importlib.metadata as m,pymc; print(sys.version); print(platform.platform()); print("source",pymc.__file__,pymc.__version__); print({n:m.version(n)for n in ["numpy","pandas","scipy","pytensor","arviz","mypy","pytest"]})'],90)
  run('freeze',['uv','pip','freeze','--python',PY],30)
  if mode=='float64':
   run('precommit',[V/'bin/pre-commit','run','--files',*FILES],600,cwd=S)
   run('no-style-rewrites',['git','diff','--exit-code'],30,cwd=S)
  state['prepare']='PASS';save()
 elif phase=='test':
  assert state['prepare']=='PASS';os.environ['PYTENSOR_FLAGS']='floatX='+mode+',base_compiledir=/work/pytensor-cache'
  run('full',[PY,'-m','pytest','-v',*['tests/test_data.py','tests/test_pytensorf.py','tests/model/test_core.py'],'--junitxml='+str(E/'full.xml')],1800,(0,1),S)
  if variant=='candidate':
   run('focused',[PY,'-m','pytest','-v','tests/test_data.py','tests/test_pytensorf.py','-k','test_data_explicit_dtype or test_set_data_explicit_dtype or test_set_data_default_conversion or test_convert_data_explicit_dtype','--junitxml='+str(E/'focused.xml')],300,cwd=S)
  if mode=='float64':run('mypy',[PY,'scripts/run_mypy.py'],600,cwd=S)
  state['source_fingerprints_after']=fingerprint();assert state['source_fingerprints_before']==state['source_fingerprints_after']
  state['state']='COMPLETE';save()
 else:raise AssertionError('UNKNOWN_PHASE')
except BaseException as error:state['error']=repr(error);save();raise
