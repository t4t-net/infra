{ pkgs, ... }:
let
  config = {
    AdvertiseServer = false;
    AllowFallingBlocks = true;
    AllowFireSpread = true;
    AllowPvP = true;
    AnalyzeMode = false;
    AntiAbuse = 0;
    BlockTickChunkRange = 5;
    BlockTickInterval = 300;
    ChatRateLimitMs = 1000;
    ClientConnectionTimeout = 1000;
    CompressPackets = true;
    ConfigVersion = "1.7";
    CorruptionProtection = true;
    DefaultRoleCode = "suplayer";
    DefaultSpawn = null;
    DieAboveErrorCount = 100000;
    DieAboveMemoryUsageMb = 50000;
    DieBelowDiskSpaceMb = 400;
    DisableModSafetyCheck = false;
    EntityDebugMode = false;
    FileEditWarning = "PLEASE NOTE: This file is also loaded when you start a single player world. If you want to run a dedicated server without affecting single player, we recommend you install the game into a different folder and run the server from there.";
    GroupChatHistorySize = 20;
    HostedMode = false;
    HostedModeAllowMods = false;
    Ip = null;
    LogBlockBreakPlace = false;
    LogFileSplitAfterLine = 500000;
    LoginFloodProtection = false;
    MapSizeX = 1024000;
    MapSizeY = 256;
    MapSizeZ = 1024000;
    MasterserverUrl = "http://masterserver.vintagestory.at/api/v1/servers/";
    MaxChunkRadius = 12;
    MaxClients = 16;
    MaxClientsInQueue = 0;
    MaxMainThreadBlockTicks = 10000;
    MaxOwnedGroupChannelsPerUser = 10;
    ModDbUrl = "https://mods.vintagestory.at/";
    ModIdBlackList = null;
    ModIdWhiteList = null;
    ModPaths = [
      "Mods"
      "/var/lib/vintagestory/Mods"
    ];
    NextPlayerGroupUid = 10;
    OnlyWhitelisted = false;
    PassTimeWhenEmpty = false;
    Password = null;
    Port = 42420;
    RandomBlockTicksPerChunk = 16;
    RegenerateCorruptChunks = false;
    RepairMode = false;
    Roles = [
      {
        AutoGrant = false;
        Code = "suvisitor";
        Color = "Green";
        DefaultGameMode = 1;
        DefaultSpawn = null;
        Description = "Can only visit this world and chat but not use/place/break anything";
        ForcedSpawn = null;
        LandClaimAllowance = 0;
        LandClaimMaxAreas = 3;
        LandClaimMinSize = {
          X = 5;
          Y = 5;
          Z = 5;
        };
        Name = "Survival Visitor";
        PrivilegeLevel = -1;
        Privileges = [ "chat" ];
        RuntimePrivileges = [ ];
      }
      {
        AutoGrant = false;
        Code = "crvisitor";
        Color = "DarkGray";
        DefaultGameMode = 2;
        DefaultSpawn = null;
        Description = "Can only visit this world, chat and fly but not use/place/break anything";
        ForcedSpawn = null;
        LandClaimAllowance = 0;
        LandClaimMaxAreas = 3;
        LandClaimMinSize = {
          X = 5;
          Y = 5;
          Z = 5;
        };
        Name = "Creative Visitor";
        PrivilegeLevel = -1;
        Privileges = [ "chat" ];
        RuntimePrivileges = [ ];
      }
      {
        AutoGrant = false;
        Code = "limitedsuplayer";
        Color = "White";
        DefaultGameMode = 1;
        DefaultSpawn = null;
        Description = "Can use/place/break blocks only in permitted areas (priv level -1), create/manage player groups and chat";
        ForcedSpawn = null;
        LandClaimAllowance = 0;
        LandClaimMaxAreas = 3;
        LandClaimMinSize = {
          X = 5;
          Y = 5;
          Z = 5;
        };
        Name = "Limited Survival Player";
        PrivilegeLevel = -1;
        Privileges = [
          "controlplayergroups"
          "manageplayergroups"
          "chat"
          "build"
          "useblock"
          "attackcreatures"
          "attackplayers"
          "selfkill"
        ];
        RuntimePrivileges = [ ];
      }
      {
        AutoGrant = false;
        Code = "limitedcrplayer";
        Color = "LightGreen";
        DefaultGameMode = 2;
        DefaultSpawn = null;
        Description = "Can use/place/break blocks in only in permitted areas (priv level -1), create/manage player groups, chat, fly and set his own game mode (= allows fly and change of move speed)";
        ForcedSpawn = null;
        LandClaimAllowance = 0;
        LandClaimMaxAreas = 3;
        LandClaimMinSize = {
          X = 5;
          Y = 5;
          Z = 5;
        };
        Name = "Limited Creative Player";
        PrivilegeLevel = -1;
        Privileges = [
          "controlplayergroups"
          "manageplayergroups"
          "chat"
          "build"
          "useblock"
          "gamemode"
          "freemove"
          "attackcreatures"
          "attackplayers"
          "selfkill"
        ];
        RuntimePrivileges = [ ];
      }
      {
        AutoGrant = false;
        Code = "suplayer";
        Color = "White";
        DefaultGameMode = 1;
        DefaultSpawn = null;
        Description = "Can use/place/break blocks in unprotected areas (priv level 0), create/manage player groups and chat. Can claim an area of up to 8 chunks.";
        ForcedSpawn = null;
        LandClaimAllowance = 262144;
        LandClaimMaxAreas = 3;
        LandClaimMinSize = {
          X = 5;
          Y = 5;
          Z = 5;
        };
        Name = "Survival Player";
        PrivilegeLevel = 0;
        Privileges = [
          "controlplayergroups"
          "manageplayergroups"
          "chat"
          "areamodify"
          "build"
          "useblock"
          "attackcreatures"
          "attackplayers"
          "selfkill"
        ];
        RuntimePrivileges = [ ];
      }
      {
        AutoGrant = false;
        Code = "crplayer";
        Color = "LightGreen";
        DefaultGameMode = 2;
        DefaultSpawn = null;
        Description = "Can use/place/break blocks in all areas (priv level 100), create/manage player groups, chat, fly and set his own game mode (= allows fly and change of move speed). Can claim an area of up to 40 chunks.";
        ForcedSpawn = null;
        LandClaimAllowance = 1310720;
        LandClaimMaxAreas = 6;
        LandClaimMinSize = {
          X = 5;
          Y = 5;
          Z = 5;
        };
        Name = "Creative Player";
        PrivilegeLevel = 100;
        Privileges = [
          "controlplayergroups"
          "manageplayergroups"
          "chat"
          "areamodify"
          "build"
          "useblock"
          "gamemode"
          "freemove"
          "attackcreatures"
          "attackplayers"
          "selfkill"
        ];
        RuntimePrivileges = [ ];
      }
      {
        AutoGrant = false;
        Code = "sumod";
        Color = "Cyan";
        DefaultGameMode = 1;
        DefaultSpawn = null;
        Description = "Can use/place/break blocks everywhere (priv level 200), create/manage player groups, chat, kick/ban players and do serverwide announcements. Can claim an area of up to 4 chunks.";
        ForcedSpawn = null;
        LandClaimAllowance = 1310720;
        LandClaimMaxAreas = 60;
        LandClaimMinSize = {
          X = 5;
          Y = 5;
          Z = 5;
        };
        Name = "Survival Moderator";
        PrivilegeLevel = 200;
        Privileges = [
          "controlplayergroups"
          "manageplayergroups"
          "chat"
          "areamodify"
          "build"
          "useblock"
          "buildblockseverywhere"
          "useblockseverywhere"
          "kick"
          "ban"
          "announce"
          "readlists"
          "attackcreatures"
          "attackplayers"
          "selfkill"
        ];
        RuntimePrivileges = [ ];
      }
      {
        AutoGrant = false;
        Code = "crmod";
        Color = "Cyan";
        DefaultGameMode = 2;
        DefaultSpawn = null;
        Description = "Can use/place/break blocks everywhere (priv level 500), create/manage player groups, chat, kick/ban players, fly and set his own or other players game modes (= allows fly and change of move speed). Can claim an area of up to 40 chunks.";
        ForcedSpawn = null;
        LandClaimAllowance = 1310720;
        LandClaimMaxAreas = 60;
        LandClaimMinSize = {
          X = 5;
          Y = 5;
          Z = 5;
        };
        Name = "Creative Moderator";
        PrivilegeLevel = 500;
        Privileges = [
          "controlplayergroups"
          "manageplayergroups"
          "chat"
          "areamodify"
          "build"
          "useblock"
          "buildblockseverywhere"
          "useblockseverywhere"
          "kick"
          "ban"
          "gamemode"
          "freemove"
          "commandplayer"
          "announce"
          "readlists"
          "attackcreatures"
          "attackplayers"
          "selfkill"
        ];
        RuntimePrivileges = [ ];
      }
      {
        AutoGrant = true;
        Code = "admin";
        Color = "LightBlue";
        DefaultGameMode = 1;
        DefaultSpawn = null;
        Description = "Has all privileges, including giving other players admin status.";
        ForcedSpawn = null;
        LandClaimAllowance = 2147483647;
        LandClaimMaxAreas = 99999;
        LandClaimMinSize = {
          X = 5;
          Y = 5;
          Z = 5;
        };
        Name = "Admin";
        PrivilegeLevel = 99999;
        Privileges = [
          "build"
          "useblock"
          "buildblockseverywhere"
          "useblockseverywhere"
          "attackplayers"
          "attackcreatures"
          "freemove"
          "gamemode"
          "pickingrange"
          "chat"
          "kick"
          "ban"
          "whitelist"
          "setwelcome"
          "announce"
          "readlists"
          "give"
          "areamodify"
          "setspawn"
          "controlserver"
          "tp"
          "time"
          "grantrevoke"
          "root"
          "commandplayer"
          "controlplayergroups"
          "manageplayergroups"
          "selfkill"
        ];
        RuntimePrivileges = [ ];
      }
    ];
    ServerDescription = null;
    ServerIdentifier = null;
    ServerLanguage = "en";
    ServerName = "Vintage Story Server";
    ServerUrl = null;
    SkipEveryChunkRow = 0;
    SkipEveryChunkRowWidth = 0;
    SpawnCapPlayerScaling = 0.5;
    StartupCommands = null;
    TemporaryIpBlockList = false;
    TickTime = 33.3333;
    Upnp = false;
    VerifyPlayerAuth = true;
    VhIdentifier = null;
    WelcomeMessage = "{0} is a faggot";
    WhitelistMode = 0;
    WorldConfig = {
      AllowCreativeMode = true;
      CreatedByPlayerName = null;
      DisabledMods = null;
      MapSizeY = null;
      PlayStyle = "surviveandbuild";
      PlayStyleLangCode = "surviveandbuild-bands";
      RepairMode = false;
      SaveFileLocation = "/var/lib/vintagestory/Saves/default.vcdbs";
      Seed = null;
      WorldConfiguration = {
        allowCoordinateHud = true;
        allowFallingBlocks = true;
        allowFireSpread = true;
        allowLandClaiming = true;
        allowMap = true;
        allowUndergroundFarming = false;
        auctionHouse = true;
        blockGravity = "sandgravel";
        bodyTemperatureResistance = "0";
        caveIns = "on";
        classExclusiveRecipes = true;
        clutterObtainable = "ifrepaired";
        colorAccurateWorldmap = false;
        creatureHostility = "aggressive";
        creatureStrength = "1";
        creatureSwimSpeed = "2";
        daysPerMonth = "20";
        deathPunishment = "drop";
        droppedItemsTimer = "600000";
        foodSpoilSpeed = "0.5";
        gameMode = "survival";
        geologicActivity = "0.05";
        globalDepositSpawnRate = "1";
        globalForestation = "0";
        globalPrecipitation = "1";
        globalTemperature = "1";
        graceTimer = "10";
        harshWinters = "true";
        landcover = "0.5";
        landformScale = "3.0";
        lightningFires = true;
        loreContent = true;
        lungCapacity = "40000";
        microblockChiseling = "cubic";
        noLiquidSourceTransport = false;
        oceanscale = "0.5";
        playerHealthPoints = "15";
        playerHealthRegenSpeed = "1";
        playerHungerSpeed = "0.6";
        playerMoveSpeed = "1.75";
        playerlives = "-1";
        playstyle = "surviveandbuild";
        polarEquatorDistance = "100000";
        propickNodeSearchRadius = "6";
        saplingGrowthRate = "1";
        seasons = "enabled";
        snowAccum = "true";
        spawnRadius = "50";
        startingClimate = "temperate";
        storyStructuresDistScaling = "1";
        surfaceCopperDeposits = "0.12";
        surfaceTinDeposits = "0.007";
        temporalGearRespawnUses = "20";
        temporalRifts = "visible";
        temporalStability = true;
        temporalStormSleeping = "0";
        temporalStorms = "sometimes";
        tempstormDurationMul = "1";
        toolDurability = "1";
        toolMiningSpeed = "1";
        upheavelCommonness = "0.3";
        worldClimate = "realistic";
        worldEdge = "traversable";
        worldHeight = 384;
        worldLength = "1024000";
        worldWidth = "1024000";
      };
      WorldName = "A new world";
      WorldType = "standard";
    };
  };
in
{
  rv32ima.machine.impermanence.extraPersistDirectories = [
    {
      path = /var/lib/vintagestory;
      mode = "0775";
      owner = "vintagestory";
      group = "vintagestory";
    }
  ];

  users.users."vintagestory" = {
    home = "/var/lib/vintagestory";
    uid = 992;
    isSystemUser = true;
    group = "vintagestory";
  };

  users.groups.vintagestory = {
    gid = 989;
  };

  systemd.sockets."vintagestory" = {
    socketConfig = {
      ListenFIFO = "/run/vintagestory.stdin";
      Service = "vintagestory.service";
    };
  };

  systemd.services."vintagestory" =
    let
      configJSON = pkgs.writeTextFile {
        name = "vintagestory-config.json";
        text = builtins.toJSON config;
      };
    in
    {
      script = ''
        rm /var/lib/vintagestory/serverconfig.json || true
        # Yes, you can make changes to your serverconfig.json, but they'll get overwritten the next time
        # you restart your server. So it's a futile affair. Make your changes through Nix or die <3
        cp "${configJSON}" /var/lib/vintagestory/serverconfig.json
        chmod 700 /var/lib/vintagestory/serverconfig.json
        ${pkgs.rv32ima.vintagestory}/VintagestoryServer --dataPath /var/lib/vintagestory
      '';
      serviceConfig = {
        Type = "simple";
        Restart = "always";
        UMask = "0002"; # Allow r/w for user & group, but not world
        User = "vintagestory";
        Sockets = "vintagestory.socket";
        StandardInput = "socket";
        StandardOutput = "journal";
        StandardError = "journal";
      };
      requires = [
        "network.target"
        "network-online.target"
      ];
      after = [
        "network.target"
        "network-online.target"
      ];
      wantedBy = [
        "multi-user.target"
      ];
    };

  networking.firewall.allowedTCPPorts = [ 42420 ];
  networking.firewall.allowedUDPPorts = [ 42420 ];
}
