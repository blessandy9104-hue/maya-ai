from pathlib import Path
print('stage: start', flush=True)
import maya_long_horizon
print('stage: module', flush=True)
import test_long_horizon_scenarios
print('stage: test_module', flush=True)
print('stage: cases', len(test_long_horizon_scenarios.PROTOTYPES), flush=True)
result = maya_long_horizon.evaluate_set(test_long_horizon_scenarios.PROTOTYPES)
print('stage: evaluated', result['status'], flush=True)
