# README for Council Session Runner

This script suite enables you to run a full Maestro Council session either with mock logic or extended to real model API integrations.
The system is designed to:

* Simulate a council of named AI agents
* Evaluate responses to a shared prompt
* Determine if a 66%+ consensus was reached
* Log full dissent and responses to `logs/session_log.json`
* Generate a human-readable Markdown summary in `docs/session_summary.md`

## Usage

From the `scripts/council` directory:

```bash
python run_council_session.py "Your question here"
```

### Example

```bash
python run_council_session.py "How can AI preserve dissent while enabling decisive action?"
```

## File Structure

```
scripts/
  council/
    run_council_session.py
    council_config.py
logs/
  session_log.json
  ...
docs/
  session_summary.md
  ...
```

## Configuration

* `council_config.py`: Contains identity and source mapping for each council member (e.g., Sol, Axion, Aria).
* The `get_mock_response()` method should be replaced with API calls for real session integration.

## Customization

* Add or remove council members in `council_config.py`
* Adjust consensus threshold logic in `run_council_session()`
* Modify Markdown structure in `generate_markdown_summary()`

## Next Steps

* Implement model API requests
* Automate versioning of session logs
* Integrate human votes into the council process

---

Built by defcon + Sol, May 2025
[https://github.com/d3fq0n1/maestro-orchestrator](https://github.com/d3fq0n1/maestro-orchestrator)
