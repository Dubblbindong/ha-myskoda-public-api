# Contributing

Thanks for your interest. This is a small project maintained by one person in
their spare time, so please keep contributions focused.

## Before you start

* Look through the open issues first. For anything bigger than a bug fix, open
  an issue and describe the idea before writing code.
* Keep the rules of the MyŠkoda Public API in mind: it is for personal use only
  and allows about **20 requests per hour and vehicle**. Do not add code that
  polls faster, and never call the real API from tests or scripts.

## Development

* Python 3.13 or newer. Tooling: `pip install aiohttp pyyaml pyflakes`
* Before submitting, run

  ```bash
  python -m pyflakes custom_components/myskoda_public_api
  python scripts/check_translations.py
  python tests/test_api_client.py
  ```

* Test your change in Home Assistant with a real vehicle and say in the pull
  request which model you used and which parts you exercised (charging,
  climate, auxiliary heating, ...). Not every vehicle supports every part.
* Keep `strings.json` and `translations/en.json` identical and
  `translations/de.json` complete.
* Do not rename entity keys or change unique IDs; they are stable once released.
* Agent-oriented notes about the code base live in [AGENTS.md](AGENTS.md).

## Pull requests

* One topic per pull request, small diffs.
* Write the description in your own words: what changed, why, and how you
  tested it.
* CI (hassfest, HACS action, lint, translation check, client test) must pass.

## Use of AI tools

* Using AI assistants for code, documentation or translations is fine. This
  integration itself was written with AI assistance and is tested by the
  maintainer on a real vehicle.
* **You are responsible for what you submit.** Read, understand and test every
  change, and be able to explain it when asked.
* **No autonomous agents.** Do not let a tool open issues, pull requests or
  comments on your behalf without your review. Such submissions are closed.
* Mention in the pull request if and how AI tools were used.
* Answers to review questions must be your own.

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities privately.
