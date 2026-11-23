{
  description = "Python development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # Choose your Python version (e.g., python312, python313, python314)
        python = pkgs.python312;

        # Python packages managed via Nix
        pythonPackages = python.withPackages (ps: with ps; [
          pip
          virtualenv
          pytest
          ruff
          # Add Nix-packaged libraries here, e.g.:
          # requests
          # fastapi
          # numpy
        ]);
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [
            pythonPackages
            pkgs.uv # Optional: fast Python package/venv manager
          ];

          # Optional: run commands automatically when entering `nix develop`
          shellHook = ''
            echo "Python environment ready: $(python --version)"
          '';
        };
      });
}
