.PHONY: report verify grade clean

# Regrade every run from raw answers and rebuild the report
report:
	python3 runner/aggregate.py
	python3 report/generate.py

# Regrade everything and fail if any number differs from the committed baseline
verify:
	python3 runner/aggregate.py
	python3 report/generate.py
	git diff --exit-code -- results/scores.csv results/summary.json \
	  && echo "VERIFY OK: regraded scores match the committed baseline" \
	  || (echo "VERIFY FAILED: regraded scores differ from committed baseline"; exit 1)

# Grade a single record: make grade REC=results/runs/t3_opus5_medium_canonical.json
grade:
	@python3 tasks/$$(python3 -c "import json,sys;d={'T1':'t01-mental-math','T2':'t02-code-trace','T3':'t03-ledger-audit','T4':'t04-constraint-gauntlet','T5A':'t05-logic-puzzles-5attr','T5B':'t05b-logic-puzzles-4attr','T6':'t06-strict-csv','T7':'t07-knowledge-recall','T8':'t08-regex-writing','T9':'t09-bug-review','T10':'t10-state-simulation','E':'e-subtle-bugs'};print(d[json.load(open('$(REC)'))['task']])")/grade.py $(REC)

clean:
	rm -f results/scores.csv results/summary.json site/report.html
