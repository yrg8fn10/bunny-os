#!/usr/bin/env bash
# shellcheck shell=bash disable=SC2034
# archiso profile definition for Bunny OS.
# https://wiki.archlinux.org/title/Archiso

iso_name="BunnyOS"
iso_label="BUNNY_OS"
iso_publisher="Bunny OS Project <https://github.com/yrg8fn10/bunny-os>"
iso_application="Bunny OS — controller-first gaming system"
iso_version="@VERSION@"
install_dir="arch"
buildmodes=('iso')
bootmodes=('uefi.systemd-boot' 'bios.syslinux')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'zstd' '-Xcompression-level' '15' '-b' '1M')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical' '--long' '-19')

file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/etc/gshadow"]="0:0:400"
  ["/etc/sudoers"]="0:0:440"
  ["/root"]="0:0:750"
  ["/root/customize_airootfs.sh"]="0:0:755"
  ["/usr/local/bin"]="0:0:755"
  ["/usr/local/lib/bunny"]="0:0:755"
  ["/opt/bunbun"]="0:0:755"
  ["/opt/bunny/panel"]="0:0:755"
)
