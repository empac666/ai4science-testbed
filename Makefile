PYTHON ?= python3
.PHONY: test dclink-check evaluate
.NOTPARALLEL:
test:
	mkdir -p $(CURDIR)/data/m2_tmp
	TMPDIR=$(CURDIR)/data/m2_tmp $(PYTHON) -m unittest discover -s tests -v
dclink-check:
	$(PYTHON) -m lab.repro dclink-check
evaluate:
	$(PYTHON) -m lab.evidence evaluate evalsets/dev --labels evalsets/dev/labels.json --out evalsets/dev/eval.json

export OMP_NUM_THREADS = 1
export OPENBLAS_NUM_THREADS = 1
export MKL_NUM_THREADS = 1
export NUMEXPR_NUM_THREADS = 1
export PYTHONDONTWRITEBYTECODE = 1
.PHONY: sweep surrogate m2
sweep:
	$(PYTHON) scripts/dclink_rebuild_preserving_split.py
surrogate:
	$(PYTHON) scripts/dclink_verify_split.py
	$(PYTHON) scripts/dclink_case.py --train
	$(PYTHON) scripts/dclink_figures.py
	$(PYTHON) scripts/dclink_case.py
	$(PYTHON) -m lab.evidence check cases/dclink_surrogate
m2:
	$(MAKE) dclink-check
	$(MAKE) sweep
	$(PYTHON) scripts/dclink_sweep.py --convergence --jobs 4
	$(MAKE) surrogate

.PHONY: sweep2 surrogate2
sweep2:
	$(PYTHON) scripts/dclink_sweep2.py --jobs 4
surrogate2:
	$(PYTHON) scripts/dclink_split2.py --verify
	$(PYTHON) scripts/dclink_case2.py --train
	$(PYTHON) scripts/dclink_figures2.py
	$(PYTHON) scripts/dclink_case2.py
	$(PYTHON) -m lab.evidence check cases/dclink_surrogate2

.PHONY: magnet
magnet:
	$(PYTHON) scripts/magnet_case.py --fetch
	$(PYTHON) scripts/magnet_case.py --igse
	$(PYTHON) scripts/magnet_figures.py
	$(PYTHON) scripts/magnet_case.py
	$(PYTHON) -m lab.evidence check cases/magnet_igse

.PHONY: design3 sweep3 surrogate3
design3:
	$(PYTHON) scripts/dclink_design3.py
	$(PYTHON) scripts/dclink_surrogate3.py --freeze-config
sweep3:
	$(PYTHON) scripts/dclink_sweep3.py --phase all --jobs 4
surrogate3:
	$(PYTHON) scripts/dclink_design3.py --verify
	$(PYTHON) scripts/dclink_case3.py --train
	$(PYTHON) scripts/dclink_figures3.py
	$(PYTHON) scripts/dclink_case3.py

.PHONY: sweep4 surrogate4
sweep4:
	$(PYTHON) scripts/dclink_sweep4.py --phase all --jobs 2
surrogate4:
	$(PYTHON) scripts/dclink_case4.py --train
	$(PYTHON) scripts/dclink_figures4.py
	$(PYTHON) scripts/dclink_case4.py --verify-results
	$(PYTHON) scripts/dclink_case4.py --export

.PHONY: sweep5 surrogate5
sweep5:
	$(PYTHON) scripts/dclink_sweep5.py --phase all --jobs 2
surrogate5:
	$(PYTHON) scripts/dclink_case5.py --train
	$(PYTHON) scripts/dclink_figures5.py
	$(PYTHON) scripts/dclink_case5.py --verify-results
	$(PYTHON) scripts/dclink_case5.py --export

.PHONY: magnet6-design magnet6-smoke magnet6-evaluate magnet6-figures
magnet6-design:
	$(PYTHON) scripts/magnet6_design.py
	$(PYTHON) scripts/magnet6_design.py --verify
magnet6-smoke:
	$(PYTHON) scripts/magnet6_arm.py --arm A1 --smoke
	$(PYTHON) scripts/magnet6_arm.py --arm M1 --smoke
	$(PYTHON) scripts/magnet6_arm.py --arm R1 --smoke
magnet6-evaluate:
	$(PYTHON) scripts/magnet6_evaluate.py
magnet6-figures:
	$(PYTHON) scripts/magnet6_figures.py

.PHONY: magnet7-design magnet7-smoke magnet7-evaluate magnet7-figures
magnet7-design:
	$(PYTHON) scripts/magnet7_design.py
	$(PYTHON) scripts/magnet7_design.py --verify
magnet7-smoke:
	$(PYTHON) scripts/magnet7_arm.py --arm A1 --smoke
	$(PYTHON) scripts/magnet7_arm.py --arm M1 --smoke
	$(PYTHON) scripts/magnet7_arm.py --arm R1 --smoke
magnet7-evaluate:
	$(PYTHON) scripts/magnet7_evaluate.py
magnet7-figures:
	$(PYTHON) scripts/magnet7_figures.py

.PHONY: magnet8-design magnet8-smoke magnet8-sweep magnet8-calibrate magnet8-evaluate magnet8-figures magnet8-test
magnet8-design:
	$(PYTHON) scripts/magnet8_design.py $(MAGNET8_DESIGN_FLAGS)
	$(PYTHON) scripts/magnet8_design.py --verify $(MAGNET8_DESIGN_FLAGS)
magnet8-smoke:
	$(PYTHON) scripts/magnet8_arm.py --exp E1 --arm A1 --smoke $(MAGNET8_DESIGN_FLAGS)
	$(PYTHON) scripts/magnet8_arm.py --exp E1 --arm M1 --smoke $(MAGNET8_DESIGN_FLAGS)
	$(PYTHON) scripts/magnet8_arm.py --exp E1 --arm R1 --smoke $(MAGNET8_DESIGN_FLAGS)
	$(PYTHON) scripts/magnet8_arm.py --exp E2 --arm A1 --smoke $(MAGNET8_DESIGN_FLAGS)
	$(PYTHON) scripts/magnet8_arm.py --exp E2 --arm M1 --smoke $(MAGNET8_DESIGN_FLAGS)
	$(PYTHON) scripts/magnet8_arm.py --exp E2 --arm R1 --smoke $(MAGNET8_DESIGN_FLAGS)
magnet8-sweep:
	$(PYTHON) scripts/magnet8_sweep.py
magnet8-calibrate:
	$(PYTHON) scripts/magnet8_calibrate.py
magnet8-evaluate:
	$(PYTHON) scripts/magnet8_evaluate.py
magnet8-figures:
	$(PYTHON) scripts/magnet8_figures.py
magnet8-test:
	$(PYTHON) -m unittest tests.test_magnet8 -v
