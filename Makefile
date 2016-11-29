CHARM=virtual-accelerator
SERIES=xenial

build: clean-build
	charm build --no-local-layers -o build $(CHARM)

charm-helpers-sync: charm-helpers
	cd $(CHARM) && \
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
