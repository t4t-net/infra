{ ipxe, writeText, ... }:
ipxe.override {
  additionalTargets = {
    "bin-x86_64-efi/ipxe.iso" = "ipxe-efi.iso";
  };

  additionalOptions = [
    "NSLOOKUP_CMD"
  ];

  embedScript = writeText "embed.ipxe" ''
    #!ipxe
    ifconf -c dhcp || goto no_dhcp
    set dns 1.1.1.1 
    goto boot

    :no_dhcp
    echo DHCP failed on all interfaces. Manual configuration required.
    echo
    ifstat
    echo
    echo Interface to configure (e.g. net0):
    read iface
    ifopen ''${iface}
    echo IP address (e.g. 192.168.1.50):
    read ip
    echo Subnet mask (e.g. 255.255.255.0):
    read mask
    echo Gateway:
    read gw
    set ''${iface}/ip ''${ip}
    set ''${iface}/netmask ''${mask}
    set ''${iface}/gateway ''${gw}
    set dns 1.1.1.1 

    :boot
    nslookup address peer2peer.sea.t4t.net
    echo DNS address: peer2peer.sea.t4t.net: ''${address}
    chain http://peer2peer.sea.t4t.net:8787/autoexec.ipxe
  '';
}
