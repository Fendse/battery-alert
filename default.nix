{ pkgs, stdenv, ... }:

stdenv.mkDerivation {
  pname = "battery-alert";
  version = "0.0.0";

  src = ./battery-alert.py;

  buildInputs = [
    (pkgs.python3.withPackages (p: with p; [ pydbus ]))
  ];

  unpackPhase = ''
    cp "$src" battery-alert.py
  '';

  buildPhase = ''
    patchShebangs battery-alert.py
  '';

  installPhase = ''
    mkdir -p "$out/bin"
    mv battery-alert.py "$out/bin/battery-alert"
  '';
}
