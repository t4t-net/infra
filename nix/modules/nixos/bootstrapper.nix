{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.rv32ima.machine.bootstrapper;
  hydraUrl = "https://hydra.tail09d5b.ts.net";

  netbootChainScript = pkgs.writeText "autoexec.ipxe" ''
    #!ipxe

    isset ''${hostname} || goto prompt_hostname
    goto boot

    :prompt_hostname
    echo
    echo Hostname to netboot (e.g. psychoboost):
    read hostname

    :boot
    chain ${cfg.baseUrl}/''${hostname}/autoexec.ipxe
  '';

  netbootServer =
    pkgs.writeScript "netboot-server"
      # python
      ''
        #!${pkgs.python3}/bin/python3
        import json
        import os
        import shutil
        import subprocess
        import urllib.request
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from pathlib import Path

        HYDRA_URL = "${hydraUrl}"
        BASE_URL = "${cfg.baseUrl}"
        NIX_STORE = "${pkgs.nix}/bin/nix-store"
        GC_ROOTS_DIR = "/nix/var/nix/gcroots/netboot-server"
        store_path_cache = {}

        def get_store_path(machine):
            if machine in store_path_cache:
                return store_path_cache[machine]
            url = f"{HYDRA_URL}/job/infra/main/nixos.{machine}-installer/latest-finished"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            path = data["buildoutputs"]["out"]["path"]
            gc_root = os.path.join(GC_ROOTS_DIR, machine)
            subprocess.run([NIX_STORE, "--add-root", gc_root, "--realise", path], check=True)
            store_path_cache[machine] = path
            return path

        class NetbootHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.strip("/")

                if path == "autoexec.ipxe":
                    data = Path("${netbootChainScript}").read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return

                parts = path.split("/", 1)
                if len(parts) != 2:
                    self.send_error(400, "expected /autoexec.ipxe or /{machine}/{file}")
                    return
                machine, filename = parts[0], parts[1]
                try:
                    store_path = get_store_path(machine)
                except Exception as e:
                    self.send_error(404, f"hydra lookup failed for {machine}: {e}")
                    return
                file_path = Path(store_path) / filename
                if not file_path.exists():
                    self.send_error(404, f"{filename} not found in {store_path}")
                    return
                if filename == "autoexec.ipxe":
                    base = f"{BASE_URL}/{machine}"
                    script = file_path.read_text()
                    script = script.replace("kernel bzImage", f"kernel {base}/bzImage")
                    script = script.replace("initrd initrd", f"initrd {base}/initrd")
                    data = script.encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_response(200)
                    self.send_header("Content-Length", str(file_path.stat().st_size))
                    self.end_headers()
                    with open(file_path, "rb") as f:
                        shutil.copyfileobj(f, self.wfile)

            def log_message(self, fmt, *args):
                print(fmt % args, flush=True)

        ThreadingHTTPServer(("", 8787), NetbootHandler).serve_forever()
      '';
in
{
  options = {
    rv32ima.machine.bootstrapper.baseUrl = lib.mkOption {
      type = lib.types.str;
      description = "base HTTP URL of this netboot server, embedded in the dispatch iPXE script";
      example = "http://peer2peer.sea.t4t.net:8787";
    };
  };

  config = {
    users.users.netboot-server = {
      isSystemUser = true;
      group = "netboot-server";
    };
    users.groups.netboot-server = { };

    nix.settings.trusted-users = [ "netboot-server" ];

    systemd.tmpfiles.rules = [
      "d /nix/var/nix/gcroots/netboot-server 0755 netboot-server netboot-server -"
    ];

    systemd.services.netboot-server = {
      description = "netboot file server (hydra-backed)";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];
      serviceConfig = {
        ExecStart = netbootServer;
        Restart = "on-failure";
        User = "netboot-server";
        Group = "netboot-server";
      };
    };

    networking.firewall.allowedTCPPorts = [ 8787 ];
  };
}
