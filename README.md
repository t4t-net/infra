# dotfiles

This is my repository containing my many NixOS configurations for hosts, as well as all of the dotfiles which I bring along with me to every system.

This repository is structured in a semi-hierarchical fashion, like so:

```
flake.nix -> The root flake into which all configurations materialize
machines/nixos -> Machine configurations for NixOS-based systems (typically servers)
machines/darwin -> Machine configurations for macOS-based systems (typically laptops)
users/ -> User configurations for all systems
modules/shared -> Shared Nix modules across all systems
modules/darwin -> Shared Nix modules for all macOS-based systems
modules/nixos -> Shared Nix modules for all NixOS-based systems
modules/home-manager -> Shared Nix modules for all home-manager configurations
{bin, fish, ghostty, git, iterm, jj, nvim, ssh, starship, tmux, wezterm} -> Typical dotfiles for applications.
```

## Installing a new machine from flake

To bootstrap a new machine requires an existing machine (of a similar architecture) which has Nix pre-installed, and can serve files on the public internet. The bootstrapping process for all new NixOS-based machines involves iPXE and netbooting an installation of NixOS with networking and SSH keys pre-configured. By using iPXE and netbooting, the time it takes to bootstrap a new machine is drastically reduced, as you're not reliant on the woes of IPMI virtual media or the like.

## Old Instructions

On the bootstrapping machine, you'll want to run:

```
MACHINE="peer2peer"
nix build "github:rv32ima/dotfiles#nixosConfigurations.${MACHINE}-installer.config.system.build.netboot"
```

This will produce a couple files in the result/ directory, including an iPXE script, a root filesystem, and a bootable Linux kernel. You'll want to serve this folder to the public internet using a HTTP web server which follows symlinks. `python3 -m http.server` is one.

Next, you'll want to boot the target system with an iPXE ISO, and get to a shell. You'll want to configure networking by running the following commands in the shell:

```
ifopen net0
set net0/ip 123.456.789.000
set net0/netmask 255.255.255.192
set net0/gateway 123.123.123.123
set dns 1.1.1.1
set hostname myhostname
```

Once you've configured networking, you'll then want to boot the NixOS image by running the following:

```
chain http://(bootstrap machine IP address):8000/autoexec.ipxe
```

## New Instructions

Use `rv32ima.machine.bootstrapTarget`. If you're connected to ghostholding in KOMO, you'll automatically be PXE booted into an iPXE image, which will then chain-load from peer2peer (which is the current bootstrapping host). If you change this value, you should redeploy to peer2peer so that the web server contents get updated with the contents of the new system-to-be-bootstrapped.

## After You've Bootstrapped

After a couple of seconds, the machine should come alive and should be available to SSH into. Once you've SSH'd in, you'll want to run these following commands to bootstrap the system for the first time. You'll see some errors relating to "could not decrypt secrets". **IT IS CRUCIAL THAT YOU DO NOT REBOOT THE SYSTEM UNTIL YOU HAVE FINISHED EVERY LAST STEP, OTHERWISE YOU WILL BE LOCKED OUT OF THE SYSTEM!**

NOTE: nixos-install will likely fail due to missing Secure Boot keys. We'll fix this later.

```
MACHINE="peer2peer"
disko --mode destroy,format,mount --flake "github:rv32ima/dotfiles?dir=nix#${MACHINE}"
sudo nixos-install --no-root-password --flake "github:rv32ima/dotfiles?dir=nix#${MACHINE}"
nixos-enter
zfs snapshot zroot/root@blank
ssh-keygen -t rsa -f /persist/etc/ssh/ssh_host_rsa_key
ssh-keygen -t ed25519 -f /persist/etc/ssh/ssh_host_ed25519_key
cat /persist/etc/ssh/ssh_host_ed25519_key.pub | nix run nixpkgs#ssh-to-age
exit
```

The last command should've produced an output that starts with `age....`. Copy that long string to .sops.yaml, and add the machine to the relevant secrets. You'll need to then run:

```
sops updatekeys nix/modules/users/*/secrets/password.yaml
```

on every file that the new machine needs access to. After you've done that, commit the new secrets to this repo, and push to GitHub. Then, on the target machine, run the following:

```
MACHINE="peer2peer"
sudo nixos-install --no-root-password --flake "github:rv32ima/dotfiles?dir=nix#${MACHINE}"
```

Once you've done that, verify that the secrets now get decrypted by running the following:

```
nixos-enter
exit
```

Now it's time to enroll the secure boot keys. Assuming the system is in setup mode (which they usually are), you'll need to run the following:

```
nixos-enter
mkdir -p /var/lib/sbctl
mount --bind /persist/var/lib/sbctl /var/lib/sbctl
sbctl create-keys
sbctl enroll-keys --microsoft
/run/current-system/bin/switch-to-configuration switch
exit
```

After you've verified that secrets can get decrypted successfully, and you've signed the bootloader with the Secure Boot keys, it's time to reboot the system. Run these following commands:

```
umount -R /mnt
zpool export -a
sync
reboot
```

Ta-da! You've bootstrapped a new machine. Pat yourself on the back.
