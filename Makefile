SERIES=xenial

build: clean
	charm build --no-local-layers -o build src

charm-helpers-sync: charm-helpers
	cd src && \
	../charm-helpers/tools/charm_helpers_sync/charm_helpers_sync.py \
	-c ./charm-helpers.yaml \
	-d ./lib/

publish: build
	bash ./publish.sh

charm-helpers:
	bzr branch lp:charm-helpers

clean-charm-helpers:
	rm -rf charm-helpers

clean:
	rm -rf build
