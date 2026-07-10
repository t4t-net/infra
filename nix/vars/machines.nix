{ ... }:
{
  "golden-experience" = {
    system = "x86_64-linux";
    stateVersion = "25.11";
    sshPublicKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMr/j1AJxcbzhfsN2iZ7cQnVzmBsJH6FcJxvT8eEUoEL";
    deployment = {
      targetHost = "golden-experience.tail09d5b.ts.net";
      targetPort = 22;
      targetUser = "root";
    };
  };
  "experimental-skin" = {
    system = "x86_64-linux";
    stateVersion = "26.05";
    machineID = "e9176ca3f729792c10ef27ed6a4ad2e2";
    sshPublicKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPL5V0jwonNuoI/xs4L35zWLRRTAND7A1e1WZu99V+kp";
    deployment = {
      targetHost = "experimental-skin.tail09d5b.ts.net";
      targetPort = 22;
      targetUser = "deploy";
    };
  };
  "ghostholding" = {
    system = "x86_64-linux";
    stateVersion = "25.11";
    machineID = "897f39ed1483490a86add609cc4570bb";
    sshPublicKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAJOdJCK9bK++zCrAqJ5qkvakYMZbcWKynbaWo4F30Jk";
    deployment = {
      targetHost = "ghostholding.tail09d5b.ts.net";
      targetPort = 22;
      targetUser = "deploy";
    };
  };
  "silver-chariot" = {
    system = "x86_64-linux";
    stateVersion = "25.11";
    sshPublicKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFQ1olIhfunqdo3YQO7qNuT894HVrw4OqWehm/KwOYSj";
    deployment = {
      targetHost = "silver-chariot.tail09d5b.ts.net";
      targetPort = 22;
      targetUser = "root";
    };
    build = {
      maxJobs = 48;
      sshUser = "nix";
      supportedFeatures = [
        "kvm"
        "benchmark"
        "big-parallel"
      ];
    };
  };
  "peer2peer" = {
    system = "x86_64-linux";
    stateVersion = "25.11";
    machineID = "b355711b63fb4686aad0e0412556e6c4";
    sshPublicKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPz54HjkBeZLYPQMrIaKxl5UmIPcNbHh8L3kNmIgiVRx";
    deployment = {
      targetHost = "peer2peer.tail09d5b.ts.net";
      targetPort = 22;
      targetUser = "deploy";
      tags = [ "auto-deploy" ];
    };
    build = {
      maxJobs = 24;
      sshUser = "nix";
      speedFactor = 10;
      supportedFeatures = [
        "kvm"
        "benchmark"
        "big-parallel"
      ];
    };
  };
  "pawpatch" = {
    system = "x86_64-linux";
    stateVersion = "26.05";
    machineID = "0032bea4f490416188be462cf964e544";
    sshPublicKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPBFwz8SD8+Yg6BYpd1geNVUsTrFSpm9tVX1dpQtDrw9";
    deployment = {
      targetHost = "pawpatch.tail09d5b.ts.net";
      targetPort = 22;
      targetUser = "deploy";
      tags = [ "auto-deploy" ];
    };
  };
  "psychoboost" = {
    system = "x86_64-linux";
    stateVersion = "26.05";
    machineID = "38c3607e2f1d4fd5ad52424acd68cdff";
    sshPublicKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOQP5dUoKULsDpiI73oZabny2hb0Cxw37Qfnnh7pM8QU";
    deployment = {
      targetHost = "psychoboost.tail09d5b.ts.net";
      targetPort = 22;
      targetUser = "deploy";
      tags = [ "auto-deploy" ];
    };
    build = {
      maxJobs = 64;
      sshUser = "nix";
      speedFactor = 10;
      supportedFeatures = [
        "kvm"
        "benchmark"
        "big-parallel"
      ];
    };
  };
  "unmusique" = {
    system = "x86_64-linux";
    stateVersion = "25.11";
    sshPublicKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEqPYLS8MYB5YCS03ID7sHxqnfkoe2yhZ1KeL3lr+quz";
    deployment = {
      targetHost = "unmusique.tail09d5b.ts.net";
      targetPort = 22;
      targetUser = "deploy";
      tags = [ "auto-deploy" ];
    };
    build = {
      maxJobs = 40;
      sshUser = "nix";
      speedFactor = 1;
      supportedFeatures = [
        "kvm"
        "benchmark"
        "big-parallel"
      ];
    };
  };
  "fadeoutz" = {
    system = "x86_64-linux";
    stateVersion = "26.05";
    machineID = "d79d558458594324a0626831b6fd86b1";
    sshPublicKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJeEX3/9e5OfsCkPw2P/hWN+tLniuNO+muL9Q9KgfJFq";
    deployment = {
      targetHost = "fadeoutz.tail09d5b.ts.net";
      targetPort = 22;
      targetUser = "deploy";
      tags = [ "auto-deploy" ];
    };
    build = {
      maxJobs = 48;
      sshUser = "nix";
      speedFactor = 1;
      supportedFeatures = [
        "kvm"
        "benchmark"
        "big-parallel"
      ];
    };
  };
}
