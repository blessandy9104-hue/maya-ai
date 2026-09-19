# Maya desktop-control simulation

The simulator models future local controls without launching real programs, sending media commands, changing brightness, changing fan settings, or modifying the host.

| Scenario | Simulated result | Host changed |
|---|---|---:|
| Open allowlisted text editor | Allowed only with `CONFIRM`; fixed executable path; planned only | No |
| Play a named song | Allowed only with media capability and `CONFIRM`; planned only | No |
| Adjust brightness | Range checked; unavailable hardware API fails closed with no-op | No |
| Cool down machine | High resource snapshot produces safe recommendations to pause Maya, stop new launches, and check physical airflow; no fan API call | No |
| Unknown application | Denied because it is not allowlisted | No |
| Emergency stop | Blocks later app and media controls | No |

Test result:

```text
{"status": "ok", "application_open_simulated": true, "song_playback_simulated": true, "brightness_fallback_safe": true, "cooling_recommendation_safe": true, "emergency_stop_blocks_controls": true, "host_changed": false}
```

Brightness and cooling are hardware-dependent. A software agent can request an approved brightness API or fan-control interface only when one is available and explicitly configured. If not available, Maya must report that limitation rather than pretending the action happened. Cooling safely begins with reducing Maya's own workload, stopping new launches, and asking the owner to check airflow; it must not alter firmware, fan curves, power settings, or other system configuration automatically.
