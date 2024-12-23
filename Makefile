run:
	uvicorn app.main:app --reload --workers 1 --host 0.0.0.0 --port 8000

install: update

update: _pip_upgrade _npm_update copy


_pip_upgrade:
	pip install --upgrade pip pip-tools
	pip-compile -U --no-header --no-annotate --strip-extras --resolver=backtracking
	pip-sync


_npm_update:
	npm update

copy:
	cp -rf ./node_modules/hyperscript.org/dist/_hyperscript.min.js ./static/js/
	cp -rf ./node_modules/htmx.org/dist/htmx.min.js ./static/js/
	cp -rf ./node_modules/@vizuaalog/bulmajs/dist/bulma.js ./static/js/
