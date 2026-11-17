"""Regression checks for GUI group-file generation using IR fork summaries."""
from pathlib import Path
import pickle
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import group_file_export as export


class GroupFileExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.root = Path(self.tmp.name)
        self.session = dict(parameters={b'TaskType': b'GoNoGo'},
            session_start_time='2026-02-01T10:00:00+01:00', dataIR={'full':np.zeros(100)},
            ResultsTable=pd.DataFrame({'TrialType':[1,1,2,2,3], 'SoundId':[10,11,12,13,14]}))
        self.analysis = dict(stay_threshold_ms=100, sample_rate_hz=2000,
            dict_data_IRxTrial={i:{'timespent_each_time':values} for i,values in
                               enumerate(([200], [], [100,200], [20], [999]))})

    def tearDown(self):
        assert self.root.resolve().is_relative_to(Path(__file__).resolve().parent)
        self.tmp.cleanup()

    def summary(self, path='one.nwb'):
        with patch.object(export,'load_session_data_fromFile',return_value=self.session), \
             patch.object(export,'detect_ir_events',return_value={}), \
             patch.object(export,'analyze_ir_by_trial',return_value=self.analysis):
            return export.extract_fork_summary(path)

    def test_duration_threshold_outcomes_and_compact_summary(self):
        result=self.summary()
        trials=result['trials']
        self.assertEqual(trials.fork_duration_ms.tolist(),[100,0,150,10])
        self.assertEqual(trials.outcome.tolist(),['Hit','Miss','FalseAlarm','Correct'])
        self.assertEqual(trials.responded.tolist(),[True,False,True,False])
        self.assertEqual(trials.trial.tolist(),[1,2,3,4])
        self.assertEqual((result['n_recorded_trials'],result['n_analyzed_trials']),(5,4))
        self.assertEqual((result['n_go'],result['n_nogo'],result['HIT'],result['CR']),(2,2,1,1))
        self.assertEqual((result['hit_pct'],result['cr_pct'],result['performance_pct']),(50,50,50))
        self.assertNotIn('dataIR',result)
        self.assertNotIn('signals',result)

    def test_real_ir_detection_and_analysis(self):
        signal = np.zeros(8500)
        signal[2200:2300] = 2
        signal[4200:4250] = 2
        markers = np.zeros(80)
        markers[[0,20,40,60]] = 99
        session = dict(parameters={'TaskType':'GoNoGo','percIRFork':'10'},
            session_start_time='2026-02-01T10:00:00+01:00',
            dataIR={'full':signal,'mean':float(signal.mean())},trialID={'full':markers},
            nTotalTrials=4,ResultsTable=pd.DataFrame({'TrialType':[1,1,2,2],'SoundId':[1,1,2,2]}))
        with patch.object(export,'load_session_data_fromFile',return_value=session):
            result=export.extract_fork_summary('actual_analysis.nwb')
        self.assertEqual(result['trials'].trial.tolist(),[2,3])
        self.assertEqual(result['trials'].fork_duration_ms.tolist(),[100,50])
        self.assertEqual(result['trials'].outcome.tolist(),['Hit','Correct'])
        self.assertEqual(result['performance_pct'],100)
        self.assertEqual(result['stay_threshold_ms'],100)

    def test_missing_animal_subfolder_is_recovered(self):
        original = self.root / "Sebastian_M5744_131409_Data.nwb"
        corrected = self.root / "M5744" / original.name
        corrected.parent.mkdir()
        corrected.touch()
        with patch.object(export,'load_session_data_fromFile',side_effect=[None,self.session]) as load, \
             patch.object(export,'detect_ir_events',return_value={}), \
             patch.object(export,'analyze_ir_by_trial',return_value=self.analysis):
            result=export.extract_fork_summary(original)
        self.assertEqual(result['file'],str(corrected))
        self.assertEqual(result['original_source_path'],str(original))
        self.assertEqual(load.call_args.args[0],corrected)

    def test_missing_path_reports_file_not_found(self):
        with patch.object(export,'load_session_data_fromFile',return_value=None):
            with self.assertRaisesRegex(FileNotFoundError,'NWB file not found'):
                export.extract_fork_summary(self.root/'Sebastian_M9999_absent.nwb')

    def test_dmts_is_skipped_before_analysis(self):
        self.session['parameters']={b'TaskType':b'DMTS'}
        with patch.object(export,'load_session_data_fromFile',return_value=self.session), \
             patch.object(export,'detect_ir_events') as detect:
            self.assertIsNone(export.extract_fork_summary('one.nwb'))
            detect.assert_not_called()

    def test_bad_trial_index_and_empty_analysis_fail(self):
        self.analysis['dict_data_IRxTrial']={99:{'timespent_each_time':[1]}}
        with self.assertRaisesRegex(ValueError,'index exceeds'):
            self.summary()
        self.analysis['dict_data_IRxTrial']={}
        with self.assertRaisesRegex(ValueError,'No eligible'):
            self.summary()

    def test_group_files_deduplicate_order_and_preserve_errors(self):
        early=self.root/'early.nwb';late=self.root/'late.nwb';bad=self.root/'bad.nwb';dmts=self.root/'dmts.nwb'
        exports={
            'one.pkl':dict(animal_name='M1',performance_by_file={str(late):{},str(early):{},str(bad):{},str(dmts):{}}),
            'duplicate.pkl':dict(animal_name='m1',performance_by_file={str(late):{}}),
            'two.pkl':dict(animal_name='M2',performance_by_file={str(early):{}})}
        calls=[]
        def reader(path):
            calls.append(path)
            if path==bad: raise ValueError('broken session')
            if path==dmts: return None
            result=self.summary(path)
            result['session_start_time']=('2026-02-02T10:00:00+01:00' if path==late else '2026-02-01T10:00:00+01:00')
            return result
        groups,sources,warnings=export.build_group_files(exports,
            {'one.pkl':'Control','duplicate.pkl':'Control','two.pkl':'Treatment'},self.root/'out',reader=reader)
        animal=groups['Control']['M1']
        self.assertEqual([s['file'] for s in animal['sessions']],[str(early),str(late)])
        self.assertEqual(calls.count(late),1)
        self.assertEqual(animal['errors'],[dict(file=str(bad),error='broken session')])
        self.assertEqual(animal['skipped_sessions'],[dict(file=str(dmts),reason='DMTS session')])
        self.assertEqual(len(sources),2)
        self.assertTrue(warnings)
        for source in sources:
            with Path(source['path']).open('rb') as stream: stored=pickle.load(stream)
            self.assertEqual(set(stored),set(groups[source['group']]))

    def test_animal_with_failed_sessions_retains_error_details(self):
        def fail(path): raise ValueError('unavailable')
        groups,sources,_=export.build_group_files(
            {'batch.pkl':dict(animal_name='M1',performance_by_file={str(self.root/'absent.nwb'):{}})},
            {'batch.pkl':'Control'},self.root/'out',reader=fail)
        self.assertEqual(groups['Control']['M1']['sessions'],[])
        self.assertEqual(len(groups['Control']['M1']['errors']),1)
        self.assertEqual(len(sources),1)

    def test_conflicting_animal_groups_rejected(self):
        payload=dict(animal_name='M1',performance_by_file={})
        with self.assertRaisesRegex(ValueError,'more than one group'):
            export.build_group_files({'one':payload,'two':payload},{'one':'Control','two':'Treatment'},self.root/'out')


if __name__=='__main__':
    unittest.main()
