.PHONY: sync check lint test

# Adapted from abuzucom/agents. The upstream lint target is kept as-is;
# the extra targets below cover this repo's own code, which the template
# has no equivalent for.

sync:
	python scripts/sync.py

check:
	python scripts/sync.py --check

lint:
	python scripts/lint_style.py
	python scripts/check_us_spelling.py AGENTS.md
	python scripts/check_english_only.py AGENTS.md
	python scripts/check_ascii.py AGENTS.md README.md CHANGELOG.md THIRD-PARTY-NOTICES.md

test:
	cd server && python -m pytest tests/
	cd ml && python -m pytest tests/
