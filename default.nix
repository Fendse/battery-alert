{ pkgs, ... }:

pkgs.stdenv.mkDerivation {
  pname = "battery-alert";
  version = "0.0.0";

  src = ./src;
  
  manpages = ./man;

  buildInputs = [
    (pkgs.python3.withPackages (p: with p; [ pydbus ]))
  ];

  unpackPhase = ''
    cp "$src/battery-alert.py" battery-alert
  '';

  buildPhase = ''
    patchShebangs battery-alert
  '';

  installPhase = ''
    mkdir -p "$out/bin"
    mv battery-alert "$out/bin/battery-alert"
    cp -r "$manpages" "$out/man"
  '';
}
