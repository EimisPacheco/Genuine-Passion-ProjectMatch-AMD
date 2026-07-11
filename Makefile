.PHONY: install migrate demo api ui test fmt clean

install:
	python3.11 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

migrate:
	. .venv/bin/activate && python -m backend.app.cli migrate

demo:
	. .venv/bin/activate && python -m backend.app.cli run --demo --top-n 3

api:
	. .venv/bin/activate && uvicorn backend.app.main:app --reload --port 8000

ui:
	cd frontend && npm run dev

test:
	. .venv/bin/activate && pytest -q

clean:
	rm -f video/out/*.mp4 video/out/*.srt video/out/*.txt
