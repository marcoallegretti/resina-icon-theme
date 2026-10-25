# SPDX-License-Identifier: EUPL-1.2
PYTHON ?= python3
PREFIX ?= /usr
BUILD ?= build/Resina
PROFILE ?= full
SOURCE_DATE_EPOCH ?= $(shell git log -1 --format=%ct 2>/dev/null)
ICONS_DIR = $(DESTDIR)$(PREFIX)/share/icons

.PHONY: all build check install uninstall dist clean

all: build

build:
	rm -rf "$(BUILD)"
	$(PYTHON) tools/build.py "$(BUILD)" --profile $(PROFILE)
	$(PYTHON) tools/validate.py "$(BUILD)" --repo .

check:
	$(PYTHON) -m unittest discover -s tests

install: build
	$(PYTHON) tools/install.py install "$(BUILD)" --icons-dir "$(ICONS_DIR)"
	$(if $(DESTDIR),,-gtk-update-icon-cache -q -t -f "$(ICONS_DIR)/Resina")

uninstall:
	$(PYTHON) tools/install.py uninstall --icons-dir "$(ICONS_DIR)"

dist: build
	@test -n "$(SOURCE_DATE_EPOCH)" || { echo "set SOURCE_DATE_EPOCH (seconds since 1970) for a reproducible archive"; exit 1; }
	$(PYTHON) tools/pack.py "$(BUILD)" resina-icon-theme.tar.xz --epoch "$(SOURCE_DATE_EPOCH)" --repo .

clean:
	rm -rf build resina-icon-theme.tar.xz resina-icon-theme.tar.xz.sha256
