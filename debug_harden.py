from maya_long_horizon import harden_scenario, evaluate_scenario
from test_long_horizon_scenarios import PROTOTYPES
unsafe = {
    'title': 'Unsafe certainty example',
    'gains': ['success'],
    'sacrifices': ['time'],
    'trajectory': 'This path will definitely become the right path.',
    'emotional_cost': 'None.',
    'risks': ['none'],
    'assumptions': ['the outcome is guaranteed'],
    'reversible_experiment': 'Commit immediately; this will work.',
}
hardened = harden_scenario(unsafe)
result = evaluate_scenario(hardened)
print(result['checks'])
print('missing=', result['missing_fields'])
print('certainty=', result['certainty_flags'])
print('probability=', result['probability_flags'])
