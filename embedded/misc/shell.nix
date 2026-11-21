with (import <nixpkgs> {});
mkShell {
  buildInputs = [
    gcc-arm-embedded
    stlink
    cmake
    ninja
    python3
    git
    pkg-config
    stlink
    tio
  ];
}
