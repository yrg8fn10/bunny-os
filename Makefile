# Bunny OS — developer entry points.
# Real ISO builds must run on Arch Linux (or the Docker target below).

SHELL := /bin/bash
ROOT  := $(CURDIR)
VERSION := $(shell tr -d '[:space:]' < VERSION)
OUT   := $(ROOT)/out
ISO   := $(OUT)/BunnyOS-installer.iso

.DEFAULT_GOAL := help
.PHONY: help preflight validate test iso iso-deck iso-docker iso-deck-docker panel panel-serve panel-deps flash clean distclean verify

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[1;35m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

preflight: ## Check host prerequisites for an ISO build
	@bash scripts/preflight.sh

validate: ## Static validation of the archiso profile and payloads
	@bash scripts/validate-profile.sh

verify: ## Fast repo integrity check (no Arch required)
	@python3 tools/verify.py

test: ## Run Bun Bun unit tests
	@cd bunbun && python3 -m unittest discover -s tests -t . -v

iso: preflight validate ## Build BunnyOS-installer.iso on this host (root required)
	@sudo ./build_bunny_os_iso.sh

iso-docker: ## Build the ISO inside a privileged Arch container
	@./build_bunny_os_iso.sh --docker

iso-deck: preflight validate ## Build the Steam Deck LCD installer ISO (root required)
	@sudo ./build_bunny_os_iso.sh --target deck

iso-deck-docker: ## Build the Steam Deck LCD ISO inside a privileged Arch container
	@./build_bunny_os_iso.sh --docker --target deck

panel-deps: ## Install Control Panel UI dev dependencies (optional)
	@cd control-panel/src-tauri && cargo fetch

panel: ## Build the native (Tauri) Control Panel shell
	@cd control-panel/src-tauri && cargo build --release
	@echo "binary: control-panel/src-tauri/target/release/bunny-panel"

panel-serve: ## Serve the dependency-free panel UI for browser testing
	@python3 -m http.server 8420 --directory control-panel/ui

flash: ## Flash the built ISO: make flash DEV=/dev/sdX
	@test -n "$(DEV)" || { echo "usage: make flash DEV=/dev/sdX"; exit 2; }
	@sudo bash scripts/flash-usb.sh "$(ISO)" "$(DEV)"

clean: ## Remove staged build tree
	@rm -rf build

distclean: clean ## Also remove produced images
	@rm -rf out
