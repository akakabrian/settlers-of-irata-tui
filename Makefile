.PHONY: all venv run clean test test-only

all: venv

venv: .venv/bin/python
.venv/bin/python:
	python3 -m venv .venv
	.venv/bin/pip install -e .

run: venv
	.venv/bin/python mule.py

test: venv
	.venv/bin/python -m tests.qa

test-only: venv
	.venv/bin/python -m tests.qa $(PAT)

clean:
	rm -rf .venv __pycache__ mule_tui/__pycache__ tests/__pycache__ \
		mule_tui.egg-info tests/out/*.svg
