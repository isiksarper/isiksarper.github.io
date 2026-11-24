# IO Kart (16 DI / 16 DO / 8 AI / 4 AO, Ethernet)

KiCad 7+ projesi. `iokart.kicad_pro` dosyasini acin; sematik bes alt sayfadan olusur.

Sematik dosyalari `tools/generate.py` tarafindan uretilir (elle duzenlemeden once bunu bilin:
betik yeniden calistirilirsa dosyalarin uzerine yazar).

    python3 tools/generate.py
    kicad-cli sch export netlist -o out/iokart.net iokart.kicad_sch
    python3 tools/verify.py        # KiCad netlist'i ile netlist_expected.txt karsilastirmasi
