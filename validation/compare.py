"""Compare actual pytest XML, preserving coverage and baseline failures."""
from pathlib import Path
import json,sys,xml.etree.ElementTree as ET,time,tempfile

def cases(path):
 root=ET.parse(path).getroot();rows={}
 for c in root.iter('testcase'):
  key=c.get('classname','')+'::'+c.attrib['name']
  status='failed' if c.find('failure') is not None or c.find('error') is not None else 'skipped' if c.find('skipped') is not None else 'passed'
  rank={'passed':0,'skipped':1,'failed':2}
  rows[key]=max([rows.get(key,'passed'),status],key=rank.get)
 assert rows,'EMPTY_SUITE'
 return rows

def assess(base,candidate,focused):
 assert len(focused)==8 and set(focused.values())=={'passed'},'EIGHT_FOCUSED_CASES_REQUIRED'
 assert set(base)<=set(candidate),'BASELINE_CASE_LOST'
 assert set(candidate)-set(base)==set(focused),'UNEXPECTED_CASE_ADDITIONS_OR_LOSSES'
 failures={k for k,v in candidate.items() if v=='failed'}
 assert failures<={k for k,v in base.items() if v=='failed'},'NEW_FAILURE'
 assert {k for k,v in candidate.items() if v=='skipped'}<={k for k,v in base.items() if v=='skipped'},'NEW_SKIP'
 assert all(candidate[k]=='passed' for k in focused),'FOCUSED_NOT_PASS_IN_FULL_SUITE'
 return {'baseline':{s:sum(v==s for v in base.values()) for s in ['passed','failed','skipped']},'candidate':{s:sum(v==s for v in candidate.values()) for s in ['passed','failed','skipped']},'retained_failure_ids':sorted(failures),'focused_pass':8}

def fixture():
 base={'ordinary':'passed','inherited':'failed','oldskip':'skipped'};focused={f'new{i}':'passed' for i in range(8)};candidate=base|focused
 assess(base,candidate,focused);assess(base,{**candidate,'inherited':'passed'},focused)
 for bad in [{k:v for k,v in candidate.items()if k!='ordinary'},{**candidate,'ordinary':'failed'},{**candidate,'ordinary':'skipped'},{**candidate,'new0':'skipped'}]:
  try:assess(base,bad,focused)
  except AssertionError:pass
  else:raise AssertionError('NEGATIVE_FIXTURE_ACCEPTED')
 with tempfile.TemporaryDirectory(prefix='pymc8467-xml-') as temp:
  path=Path(temp)/'pytest.xml'
  path.write_text('<testsuites><testsuite><testcase classname="tests.test_data.TestData" name="test_bool[bool]"/><testcase classname="tests.test_data" name="old"><failure message="assertion"/></testcase><testcase classname="tests.test_data" name="skip"><skipped/></testcase></testsuite></testsuites>')
  assert cases(path)=={'tests.test_data.TestData::test_bool[bool]':'passed','tests.test_data::old':'failed','tests.test_data::skip':'skipped'}
  for text,expected in [
   ('<testsuite><testcase name="inherited"><error message="setup"/></testcase></testsuite>',{'::inherited':'failed'}),
   ('<testsuite><testcase name="same"/><testcase name="same"><error message="teardown"/></testcase></testsuite>',{'::same':'failed'}),
   ('<testsuite><testcase name="same"><failure/></testcase><testcase name="same"/></testsuite>',{'::same':'failed'}),
  ]:
   path.write_text(text);assert cases(path)==expected
  inherited={'::inherited':'failed'};focus={f'new{i}':'passed'for i in range(8)}
  assess(inherited,inherited|focus,focus)
  path.write_text('<testsuite><testcase name="newcollection"><error message="collection failure"/></testcase></testsuite>')
  newerror=cases(path)
  for badcandidate in [inherited|focus|newerror,{'ordinary':'failed'}|focus]:
   try:assess({'ordinary':'passed'} if 'ordinary' in badcandidate else inherited,badcandidate,focus)
   except AssertionError:pass
   else:raise AssertionError('CANDIDATE_ONLY_ERROR_ACCEPTED')
  path.write_text('<testsuites/>')
  try:cases(path)
  except AssertionError:pass
  else:raise AssertionError('EMPTY_XML_ACCEPTED')
 print('COMPARISON_AND_REAL_XML_POSITIVE_NEGATIVE_FIXTURES_PASS')

if __name__=='__main__':
 if sys.argv[1:]==['--fixture']:fixture();sys.exit(0)
 root,output=map(Path,sys.argv[1:]);result={'state':'INCOMPLETE','variants':{}}
 try:
  states={}
  for variant in ['baseline','candidate']:
   for mode in ['float64','float32']:
    folder=root/f'proof-{variant}-{mode}';state=json.loads((folder/'state.json').read_text());host=json.loads((folder/'host.json').read_text())
    assert state['state']==host['state']=='COMPLETE' and state['variant']==variant and state['floatX']==mode
    assert not host['OOMKilled'] and host['container_stopped'] and time.time()<state['origin']+3000,'HOST_OR_COMMON_DEADLINE'
    assert state['source_fingerprints_before']==state['source_fingerprints_after'],'SOURCE_DRIFT'
    states[variant,mode]=state
  for mode in ['float64','float32']:
   b=root/f'proof-baseline-{mode}';c=root/f'proof-candidate-{mode}'
   result['variants'][mode]=assess(cases(b/'full.xml'),cases(c/'full.xml'),cases(c/'focused.xml'))
  b=root/'proof-baseline-float64';c=root/'proof-candidate-float64'
  assert (b/'mypy.stdout').read_bytes()==(c/'mypy.stdout').read_bytes(),'MYPY_STDOUT_DRIFT'
  assert (b/'mypy.stderr').read_bytes()==(c/'mypy.stderr').read_bytes(),'MYPY_STDERR_DRIFT'
  bc=next(x['exit']for x in states['baseline','float64']['commands']if x['label']=='mypy');cc=next(x['exit']for x in states['candidate','float64']['commands']if x['label']=='mypy')
  assert bc==cc==0,'MYPY_EXIT_DRIFT_OR_UNEXPECTED_RESULTS';result['mypy_exit']=cc;result['mypy_output']='BYTE_IDENTICAL'
  result['state']='COMPLETE_NO_NEW_FAILURES_OR_SKIPS_EIGHT_FOCUSED_PASS_BOTH_MODES'
 except BaseException as error:result['error']=repr(error);raise
 finally:output.write_text(json.dumps(result,indent=2)+'\n')
