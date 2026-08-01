PYTHON ?= python3

.PHONY: test quick lint format-check package figures benchmark resilience clean

test:
	$(PYTHON) -m unittest discover -s tests -v

quick:
	$(PYTHON) -m unittest discover -s tests -v

lint:
	ruff check src scripts tests

format-check:
	python3 -m compileall src scripts tests

package:
	$(PYTHON) -m build

figures:
	$(PYTHON) scripts/generate_phase7_figures.py

benchmark:
	bash scripts/run_phase6.sh

resilience:
	bash scripts/run_phase7.sh

clean:
	rm -rf build dist .pytest_cache .ruff_cache .mypy_cache htmlcov
