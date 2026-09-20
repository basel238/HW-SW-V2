"""Session isolation, fail-fast correctness and script routing integration tests."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / 'repo with spaces'
        self.repo.mkdir()
        for folder in ('lib', 'config'):
            shutil.copytree(ROOT / folder, self.repo / folder)
        (self.repo / 'tools').mkdir()
        for name in ('doctor.sh', 'compare.sh', 'gen_report.sh', 'ab_timing.sh'):
            shutil.copy2(ROOT / 'tools' / name, self.repo / 'tools' / name)
        for name in ('run_all.sh', 'script_nbody.sh', 'script_raytrace.sh'):
            shutil.copy2(ROOT / name, self.repo / name)
        for folder in ('bench', 'variants', 'upstream', 'bin'):
            (self.repo / folder).mkdir()
        fake = '''import os, sys, json
from pathlib import Path
a=sys.argv[1:]
mode=a[a.index('--mode')+1]
with open(os.environ['CALLS'], 'a') as f: f.write(json.dumps([Path(__file__).name,a])+'\\n')
if mode=='calibrate': print(2)
elif mode=='verify':
    if os.environ.get('FAIL_VERIFY') and '_opt' in __file__: sys.exit(7)
    print('verify: OK')
else:
    if os.environ.get('FAIL_RAW'): sys.exit(9)
    print('RESULT total_sec=0.010000 loops='+a[a.index('--loops')+1])
'''
        for bench in ('nbody', 'raytrace'):
            for directory, suffix in (('bench', ''), ('variants', '_opt'), ('upstream', '')):
                (self.repo / directory / f'bm_{bench}_upstream{suffix}.py').write_text(fake)
            (self.repo / f'report_{bench}.txt').write_text('Authored report with [TODO] still present\n')
        # Calling Git or perf is a test failure even if the shell suppresses it.
        for tool in ('git', 'perf'):
            p = self.repo / 'bin' / tool
            p.write_text('#!/bin/sh\necho '+tool+' >> "$FORBIDDEN"\nexit 99\n')
            p.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.repo/'bin')+os.pathsep+os.environ['PATH'],
                        RESULTS_DIR=str(self.repo/'results'), USE_UPSTREAM='1',
                        SKIP_WORKLOAD_VERIFY='1', USE_TASKSET='0', CLEAN_REPS='1',
                        PY_REL=sys.executable, PY_DBG=sys.executable, ENABLE_VERIFY='1',
                        CAPTURE_GIT_METADATA='0', PYTHONDONTWRITEBYTECODE='1',
                        CALLS=str(self.repo/'calls.jsonl'), FORBIDDEN=str(self.repo/'forbidden'))

    def run_script(self, script, *args, **env):
        return subprocess.run(['bash', str(self.repo/script), *args], cwd=self.repo,
                              env=dict(self.env, **env), text=True, capture_output=True, timeout=30)

    def test_full_selection_time_only_and_exact_sessions(self):
        # Stale convenience pointers must not influence the new session.
        (self.repo/'results').mkdir()
        stale = self.repo/'results'/'stale'
        stale.mkdir()
        for b in ('nbody', 'raytrace'):
            (self.repo/'results'/f'latest_{b}_optimized').symlink_to('stale')
        p = self.run_script('run_all.sh', '--time-only')
        self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
        session, = (self.repo/'results').glob('session_all_*')
        calls = [json.loads(x) for x in (self.repo/'calls.jsonl').read_text().splitlines()]
        for bench, kernel in (('nbody', 'flat_pow'), ('raytrace', 'full')):
            refs = dict(line.split('\t',1) for line in (session/f'{bench}.tsv').read_text().splitlines())
            self.assertNotIn('latest', refs['baseline']+refs['optimized'])
            self.assertTrue(Path(refs['comparison']).is_dir())
            for name, args in calls:
                if bench not in name: continue
                if '--mode' in args and args[args.index('--mode')+1] in ('verify','raw'):
                    self.assertEqual(args[args.index('--loops')+1], '2')
                if '_opt' in name:
                    self.assertEqual(args[args.index('--kernel')+1], kernel)
            self.assertEqual((self.repo/f'report_{bench}.txt').read_text(), 'Authored report with [TODO] still present\n')
            manifest = (Path(refs['optimized'])/'manifest.txt').read_text()
            self.assertIn('source sha256:', manifest)
            self.assertIn('CAPTURE_GIT_METADATA=0', manifest)
        # Metadata may check perf --version even though perf execution is disabled.
        # It must not execute any perf command in time-only mode.
        self.assertFalse((self.repo/'forbidden').exists())

    def test_full_workflow_surfaces_unavailable_profilers(self):
        # Replace only preflight and external Linux perf; real pipeline,
        # cProfile, correctness, timing, comparison and session code still run.
        doctor=self.repo/'tools/doctor.sh'
        doctor.write_text('#!/bin/sh\nexit 0\n')
        p=self.run_script('run_all.sh','--loops','2')
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        session,=(self.repo/'results').glob('session_all_*')
        for bench in ('nbody','raytrace'):
            refs=dict(line.split('\t',1) for line in (session/f'{bench}.tsv').read_text().splitlines())
            for arm in ('baseline','optimized'):
                directory=Path(refs[arm])
                status=(directory/'phases.tsv').read_text()
                self.assertIn('perf_record\tunavailable',status)
                self.assertIn('perf_stat\tunavailable',status)
                self.assertTrue((directory/f'raw/cprofile_{arm}.pstats').exists())
        self.assertNotIn('git',(self.repo/'forbidden').read_text().splitlines())

    def test_verification_failure_prevents_optimized_timing(self):
        p = self.run_script('script_nbody.sh', '--time-only', '--loops','3', FAIL_VERIFY='1')
        self.assertNotEqual(p.returncode, 0)
        calls=[json.loads(x) for x in (self.repo/'calls.jsonl').read_text().splitlines()]
        self.assertFalse(any('_opt' in n and '--mode' in a and a[a.index('--mode')+1]=='raw' for n,a in calls))
        self.assertFalse(list((self.repo/'results').glob('session_*/comparison_nbody')))

    def test_failed_timing_is_not_silently_dropped(self):
        p = self.run_script('script_nbody.sh','--time-only','--loops','1',FAIL_RAW='1')
        self.assertNotEqual(p.returncode,0)
        self.assertIn('clean timing rep 1 failed',p.stderr)

    def test_ab_kernel_forwarding_and_balanced_order(self):
        p=self.run_script('tools/ab_timing.sh','nbody','4','--kernel','grouped',LOOPS='2')
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        out,= (self.repo/'results').glob('abtiming_nbody_*')
        import csv
        rows=list(csv.DictReader((out/'samples.csv').read_text().splitlines()))
        self.assertEqual([r['variant'] for r in rows], ['baseline','optimized','optimized','baseline']*2)
        calls=[json.loads(x) for x in (self.repo/'calls.jsonl').read_text().splitlines()]
        for name,args in calls:
            if '_opt' in name: self.assertEqual(args[args.index('--kernel')+1],'grouped')
        self.assertIn('round resamples',(out/'summary.txt').read_text())

    def test_evidence_generator_refuses_existing_authored_report(self):
        directory=self.repo/'dummy';directory.mkdir()
        report=self.repo/'report_nbody.txt'
        p=self.run_script('tools/gen_report.sh','nbody',str(directory),str(directory),str(directory),str(report))
        self.assertNotEqual(p.returncode,0)
        self.assertIn('[TODO]',report.read_text())


if __name__ == '__main__': unittest.main()
