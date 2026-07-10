{
  ...
}:
{
  disko.devices.disk.disk1 = {
    type = "disk";
    device = "/dev/disk/by-id/nvme-Samsung_SSD_990_PRO_1TB_S7LANL0L421692Z";
    content.type = "gpt";
    content.partitions = {
      ESP = {
        size = "500M";
        type = "EF00";
        content = {
          type = "filesystem";
          format = "vfat";
          mountpoint = "/boot";
          mountOptions = [ "umask=0077" ];
        };
      };
      luks-swap = {
        size = "32G";
        content = {
          type = "luks";
          name = "disk1-luks-swap";
          settings = {
            allowDiscards = true;
          };
          content = {
            type = "swap";
            discardPolicy = "both";
          };
        };
      };
      luks-zroot = {
        size = "100%";
        content = {
          type = "luks";
          name = "disk1-luks-zroot";
          settings = {
            allowDiscards = true;
          };
          content = {
            type = "zfs";
            pool = "zroot";
          };
        };
      };
    };
  };

  disko.devices.zpool.zroot = {
    type = "zpool";
    mode.topology = {
      type = "topology";
      vdev = [
        {
          members = [
            "/dev/mapper/disk1-luks-zroot"
          ];
        }
      ];
    };
    options = {
      ashift = "12";
    };
    rootFsOptions = {
      acltype = "posixacl";
      atime = "off";
      compression = "zstd";
      mountpoint = "none";
      xattr = "sa";
      "com.sun:auto-snapshot" = "false";
    };
    datasets = {
      root = {
        type = "zfs_fs";
        mountpoint = "/";
        options.mountpoint = "legacy";
      };
      home = {
        type = "zfs_fs";
        mountpoint = "/home";
        options.mountpoint = "legacy";
      };
      persist = {
        type = "zfs_fs";
        mountpoint = "/persist";
        options.mountpoint = "legacy";
      };
      nix = {
        type = "zfs_fs";
        mountpoint = "/nix";
        options.mountpoint = "legacy";
      };
    };
  };

  fileSystems."/persist".neededForBoot = true;
  boot.loader.efi.canTouchEfiVariables = true;
}
