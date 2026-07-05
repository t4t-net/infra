---
name: project_bao_secrets_migration
description: Future goal to replace sops-nix with OpenBao secrets pulled via mTLS using ACME-provisioned machine certs from step-ca
metadata: 
  node_type: memory
  type: project
  originSessionId: 03f7a6c6-69dd-4666-adc0-1ab20cc5ae00
---

Ellie wants to migrate away from sops-nix to a system where machines pull secrets directly from OpenBao using mTLS, authenticated by TLS certs they provision from step-ca via ACME.

**Why:** Eliminates age key management entirely — no more .sops.yaml key_groups per machine, no rekeying when adding hosts. Trust chain is: step-ca (root of trust) → ACME proves domain ownership → bao cert auth trusts step-ca-signed certs → machine pulls its own secrets.

**How to apply:** When working on openbao or step-ca modules, keep this migration goal in mind. New sops secrets added in the interim are fine but should be considered temporary.

Key open design questions (as of 2026-07-04):
- Where does bao run? (one of ellie's machines or external?)
- Is cert auth method already wired up in the openbao module?
- Bootstrap story: NixOS activation script needs to pull secrets BEFORE services start (same role sops-nix plays today) — requires valid ACME cert + bao reachable at boot
- Secret persistence: tmpfs (re-pull every boot, bao must be reachable) vs persisted (better resilience, slightly weaker security)

Related: [[project_dotfiles]], openbao module at `nix/modules/nixos/services/openbao/`, step-ca ACME provisioner already set up with `maxTLSCertDuration = "8760h"`
