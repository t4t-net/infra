{
  config,
  pkgs,
  lib,
  inputs,
  ...
}:
{
  home-manager.users."${config.system.primaryUser}" = { config, ... }: {
    programs.neovim = {
      enable = true;
      vimAlias = true;
      vimdiffAlias = true;

      extraPackages = with pkgs; [
        git
        lazygit
        ripgrep
        fzf
        fd
        tree-sitter

        jj
        jjui

        direnv

        markdownlint-cli2

        # Language servers
        # Python
        python313Packages.python-lsp-server
        python313Packages.python-lsp-black
        # Lua
        lua-language-server
        # Yaml
        yaml-language-server
        # Nix
        nixd
        nixfmt
        statix
        # Terraform
        terraform-lsp

      ];

      plugins = with pkgs.vimPlugins; [
        lazy-nvim
      ];

      initLua =
        let
          treesitter = pkgs.vimPlugins.nvim-treesitter.withAllGrammars;

          # NOTE: when using only a few treesitter grammars, make sure
          # to clear ensure_installed in nvim-treesitter (see below)
          # treesitter = pkgs.vimPlugins.nvim-treesitter.withPlugins (p: [
          #   p.lua
          #   p.nix
          # ]);

          # Collect all grammar derivations into a single directory
          # so nvim-treesitter can find them via install_dir
          treesitterGrammars = pkgs.symlinkJoin {
            name = "nvim-treesitter-grammars";
            paths = treesitter.dependencies;
          };

          # List of all plugins that you want to use.
          # These get turned into a linkFarm directory that Lazy uses
          # as its dev.path (see below).
          plugins = with pkgs.vimPlugins; [
            # keep-sorted start block=yes

            LazyVim
            SchemaStore-nvim
            blink-cmp
            bufferline-nvim
            claudecode-nvim
            conform-nvim
            dressing-nvim
            flash-nvim
            flatten-nvim
            friendly-snippets
            fzf-lua
            gitsigns-nvim
            grug-far-nvim
            lazy-nvim
            lazydev-nvim
            lualine-nvim
            markdown-preview-nvim
            mason-nvim-dap-nvim
            mini-ai
            mini-icons
            mini-pairs
            neo-tree-nvim
            neotest
            neotest-python
            noice-nvim
            none-ls-nvim
            nui-nvim
            nvim-cmp
            nvim-dap
            nvim-dap-python
            nvim-lint
            nvim-lspconfig
            nvim-nio
            nvim-treesitter
            nvim-treesitter-textobjects
            nvim-ts-autotag
            persistence-nvim
            pkgs.rv32ima.direnv-nvim
            pkgs.rv32ima.jj-diffconflicts
            pkgs.rv32ima.lazyjui-nvim
            pkgs.rv32ima.sops-nvim
            pkgs.rv32ima.telescope-terraform-doc-nvim
            pkgs.rv32ima.telescope-terraform-nvim
            plenary-nvim
            render-markdown-nvim
            snacks-nvim
            telescope-fzf-native-nvim
            telescope-nvim
            todo-comments-nvim
            tokyonight-nvim
            trouble-nvim
            ts-comments-nvim
            venv-selector-nvim
            which-key-nvim
            # When a plugin's name in nixpkgs doesn't match what Lazy expects,
            # you can manually specify the mapping like this:
            {
              name = "catppuccin";
              path = catppuccin-nvim;
            }
            # keep-sorted end
          ];

          # Maps a plugin derivation to a { name, path } pair.
          # linkFarm expects this format to create a directory of symlinks
          # where each plugin is accessible by its name.
          mkEntryFromDrv =
            drv:
            if lib.isDerivation drv then
              {
                name = "${lib.getName drv}";
                path = drv;
              }
            else
              drv;

          # Creates a directory with symlinks to all plugins, keyed by name.
          # This is what Lazy uses as its local plugin source via dev.path.
          lazyPath = pkgs.linkFarm "lazy-plugins" (builtins.map mkEntryFromDrv plugins);
        in
        # lua
        ''
          require("lazy").setup({
            defaults = {
              lazy = true,
            },
            dev = {
              -- reuse files from pkgs.vimPlugins.*
              path = "${lazyPath}",
              patterns = { "." },
              -- if a plugin isn't found in the linkFarm,
              -- Lazy will fall back to downloading it directly
              fallback = true,
            },
            spec = {
              { "LazyVim/LazyVim", import = "lazyvim.plugins" },

              -- here you can enable extras like this:
              -- { import = "lazyvim.plugins.extras.editor.aerial" }, -- sybmols

              -- language specific config is often available via an extra
              -- find available languages here: https://www.lazyvim.org/extras or via :LazyExtras
              { import = "lazyvim.plugins.extras.ai.claudecode" },
              { import = "lazyvim.plugins.extras.lang.nix" },
              { import = "lazyvim.plugins.extras.lang.json" },
              { import = "lazyvim.plugins.extras.lang.markdown" },
              { import = "lazyvim.plugins.extras.lang.toml" },
              { import = "lazyvim.plugins.extras.lang.python" },
              { import = "lazyvim.plugins.extras.lang.terraform" },
              { import = "lazyvim.plugins.extras.lang.zig" },
              { import = "lazyvim.plugins.extras.editor.telescope" },
              -- { import = "lazyvim.plugins.extras.lang.nix" }, -- configure lsp/formatters/treesitter etc. for nix 

              -- disable mason.nvim, use programs.neovim.extraPackages
              { "mason-org/mason-lspconfig.nvim", enabled = false },
              { "mason-org/mason.nvim", enabled = false },

              -- import/override with your plugins
              { import = "plugins" },

              -- since mason is disabled, each server needs to be explicitly
              -- configured here so nvim-lspconfig picks it up without mason
              { "neovim/nvim-lspconfig", opts = { servers = lsp_servers }},


              {
                "mrdwarf7/lazyjui.nvim",
                dependencies = {
                  "nvim-lua/plenary.nvim"
                },
                keys = {
                  {
                    "<Leader>jj",
                    function()
                      require("lazyjui").open()
                    end,
                  },
                },
                opts = {
                  cmd = {
                    "${pkgs.jjui}/bin/jjui"
                  },
                },
              },


              -- make sure nvim-treesitter is configured last,
              -- if you dont want to install all grammars you might
              -- need to use a function for ensure_installed to
              -- clear it
              {
                "nvim-treesitter/nvim-treesitter",
                -- dont run anything when installing/updating
                build = "",
                -- NOTE: when not all grammars are installed, make sure
                -- to clear encure_installed by making opts a function:
                -- opts = function(_, opts)
                --   opts.ensure_installed = {}
                --   opts.install_dir = "${treesitterGrammars}"
                --   return opts
                -- end,
                opts = {
                  install_dir = "${treesitterGrammars}",
                },
              },
            },
            -- see https://www.lazyvim.org/plugins/colorscheme on how to change/install colorschemes 
            install = { colorscheme = { "habamax", "catppuccin" } },
            checker = { enabled = false }, -- disable automatic update checking
          })
        '';
    };

    xdg.configFile."nvim/lua" = {
      recursive = true;
      source = config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/.dotfiles/nvim/lua";
    };
  };
}
