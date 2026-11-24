#!/usr/bin/env python3
"""Generates the IO card KiCad schematic (16 DI + 16 DO + 8 AI + 4 AO, Ethernet).

Run:  python3 tools/generate.py     (writes ../*.kicad_sch, ../lib/iokart.kicad_sym, ../netlist_expected.txt)
"""
import os
import kisch
from kisch import NC

OUT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
R, C, CP, L, FB = "Device:R", "Device:C", "Device:C_Polarized", "Device:L", "Device:FerriteBead"
LED, DS, PTC, FUSE = "Device:LED", "Device:D_Schottky", "Device:Polyfuse", "Device:Fuse"

# ---------------------------------------------------------------- custom symbols (pinouts from datasheets)
os.makedirs(os.path.join(OUT, "lib"), exist_ok=True)
IN_PINS = [1, 3, 5, 8, 10, 12, 14, 18]
LED_PINS = [2, 4, 6, 9, 11, 13, 15, 19]
OUT_PINS = [35, 34, 33, 32, 31, 30, 29, 28]
left = []
for k in range(8):
    left += [(str(IN_PINS[k]), "IN%d" % (k + 1), "passive"), (str(LED_PINS[k]), "LED%d" % (k + 1), "passive")]
left += [None, ("16", "AVCC", "power_in"), ("7", "AVSS", "power_in"), ("17", "AVSS", "power_in")]
right = [("37", "VCC1", "power_in"), ("38", "COMM_SEL", "input"), None]
right += [(str(OUT_PINS[k]), "OUT%d" % (k + 1), "tri_state") for k in range(8)]
right += [None, ("27", "OUT_EN", "input"), ("24", "F0", "input"), ("23", "F1", "input"),
          ("26", "nFAULT", "open_collector"), None, ("20", "NC", "no_connect"), ("22", "NC", "no_connect"),
          None, ("21", "GND1", "power_in"), ("25", "GND1", "power_in"), ("36", "GND1", "power_in")]
kisch.make_symbol("iokart", "ISO1228", left, right, "Package_SO:SSOP-38",  # DFB 38-pin, verify footprint
                  "https://www.ti.com/lit/ds/symlink/iso1228.pdf")
kisch.make_symbol(
    "iokart", "DAC80504",
    [("7", "VDD", "power_in"), ("16", "VIO", "power_in"), None, ("1", "REF", "passive"), None,
     ("8", "GAIN", "input"), ("9", "RSTSEL", "input"), ("10", "REFDIV", "input"), ("11", "LDAC", "input"),
     None, ("6", "GND", "power_in"), ("17", "PAD", "passive")],
    [("2", "OUT0", "output"), ("3", "OUT1", "output"), ("4", "OUT2", "output"), ("5", "OUT3", "output"),
     None, ("12", "CS", "input"), ("13", "SCLK", "input"), ("14", "SDI", "input"),
     ("15", "SDO", "tri_state")],
    "Package_DFN_QFN:WQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm", "https://www.ti.com/lit/ds/symlink/dac80504.pdf",
    width=20.32)
kisch.write_lib("iokart", os.path.join(OUT, "lib", "iokart.kicad_sym"))

P = kisch.Project("iokart", "IO Kart - 16 DI / 16 DO / 8 AI / 4 AO - Ethernet")


class Bank:
    """Column of horizontal two-pin parts."""

    def __init__(self, sheet, x, y, pitch=7.62):
        self.s, self.x, self.y, self.pitch = sheet, x, y, pitch

    def add(self, lib, prefix, value, a, b):
        r = self.s.two(lib, prefix, value, a, b, self.x, self.y, horiz=True)
        self.y += self.pitch
        return r


class Row:
    """Row of vertical two-pin parts."""

    def __init__(self, sheet, x, y, pitch=12.7):
        self.s, self.x, self.y, self.pitch = sheet, x, y, pitch

    def add(self, lib, prefix, value, a, b):
        r = self.s.two(lib, prefix, value, a, b, self.x, self.y, horiz=False)
        self.x += max(self.pitch, 6.5 + 1.2 * len(value))
        return r


# ================================================================ 1. BESLEME VE IZOLASYON
s = P.sheet("besleme", "1 - Besleme ve izolasyon", "A3")
s.text("24 V GIRIS (L+ / M / PE): PTC sigorta, ters polarite diyotu, TVS, ortak mod filtresi", 20, 20)
s.part("Connector:Screw_Terminal_01x03", "J", "L+ / M / PE", 50, 45,
       {"1": "VIN_L", "2": "GNDPWR", "3": "Earth"}, refpos=(52, 37))
b = Bank(s, 100, 35)
b.add(PTC, "F", "PTC 500mA 60V", "VIN_L", "VIN_F")
r = Row(s, 150, 45)
r.add(DS, "D", "SS16 (60V 1A)", "+24V", "VIN_F")
r.add("Diode:SMAJ33CA", "D", "SMAJ33CA", "+24V", "GNDPWR")
r.add(C, "C", "10uF 50V", "+24V", "GNDPWR")
r.add(C, "C", "100nF 50V", "+24V", "GNDPWR")
s.part("Device:Filter_EMI_CommonMode", "FL", "CMC 2x1mH 1A", 235, 45,
       {"1": "+24V", "2": "VDC_P", "3": "GNDPWR", "4": "VDC_N"}, refpos=(235, 36))
s.text("IZOLE DC-DC 24 V -> 5 V (saha / lojik bariyeri)", 270, 20)
r = Row(s, 285, 75, pitch=15.24)
r.add(C, "C", "10uF 50V", "VDC_P", "VDC_N")
r.add(C, "C", "100nF 50V", "VDC_P", "VDC_N")
s.part("Converter_DCDC:TMR4-2411WI", "PS", "TMR 4-2411WI (9-36V -> 5V 0.8A)", 330, 45,
       {"+Vin": "VDC_P", "-Vin": "VDC_N", "OnOff": NC, "NC": NC, "+Vout": "+5V", "-Vout": "GND"},
       refpos=(330, 34))
s.flag("VDC_P", 350, 80)
s.flag("VDC_N", 365, 80)

s.text("LOJIK RAYLARI: +5V, +3V3 (LDO), +5VA (ferrit), GND / GNDA tek noktadan", 20, 105)
r = Row(s, 30, 130)
r.add(C, "C", "22uF 10V", "+5V", "GND")
r.add(C, "C", "100nF", "+5V", "GND")
r.add(C, "C", "10uF 10V", "+5V", "GND")
s.part("Regulator_Linear:AMS1117-3.3", "U", "AMS1117-3.3", 95, 125,
       {"VI": "+5V", "VO": "+3V3", "GND": "GND"}, refpos=(95, 116))
r = Row(s, 125, 130)
r.add(C, "C", "22uF 10V", "+3V3", "GND")
r.add(C, "C", "100nF", "+3V3", "GND")
r.x += 12
r.add(FB, "FB", "600R@100MHz", "+5V", "+5VA")
r.x += 6
r.add(C, "C", "10uF 10V", "+5VA", "GNDA")
r.add(C, "C", "100nF", "+5VA", "GNDA")
r.x += 12
r.add(R, "R", "0R (GNDA-GND baglantisi, ADC altinda)", "GNDA", "GND")
r.x += 40
s.text("PE: sase kuplaji", 300, 105)
r = Row(s, 310, 130, pitch=20)
r.add(C, "C", "1nF 2kV", "GND", "Earth")
r.add(R, "R", "1M", "GND", "Earth")
r.add(C, "C", "1nF 2kV", "GNDPWR", "Earth")

s.text("+15V BOOST (AO opamp beslemesi) - LM27313, Vout = 1.23 V x (1 + 150k/13.3k) = 15.1 V", 20, 170)
s.part("Regulator_Switching:LM27313XMF", "U", "LM27313XMF", 60, 200,
       {"VIN": "+5V", "EN": "+5V", "SW": "SW15", "FB": "FB15", "GND": "GND"}, refpos=(60, 189))
b = Bank(s, 120, 190)
b.add(L, "L", "10uH 1A", "+5V", "SW15")
b.add(DS, "D", "MBR0530", "V15_RAW", "SW15")
b.add(R, "R", "150k 1%", "V15_RAW", "FB15")
b.add(C, "C", "220pF", "V15_RAW", "FB15")
b.add(FB, "FB", "600R@100MHz", "V15_RAW", "+15V")
r = Row(s, 185, 200)
r.add(R, "R", "13.3k 1%", "FB15", "GND")
r.x += 6
r.add(C, "C", "4.7uF 25V", "V15_RAW", "GND")
r.add(C, "C", "10uF 25V", "+15V", "GNDA")
r.add(C, "C", "100nF 25V", "+15V", "GNDA")
r.add(C, "C", "10uF 10V", "+5V", "GND")

s.text("-5V SARJ POMPASI (opamp cikisinin 0 V'a inebilmesi icin) - TPS60403", 250, 170)
s.part("Regulator_SwitchedCapacitor:TPS60403DBV", "U", "TPS60403DBV", 285, 200,
       {"IN": "+5V", "OUT": "N5_RAW", "C_{FLY+}": "CFLY_P", "C_{FLY-}": "CFLY_N", "GND": "GND"},
       refpos=(285, 187))
b = Bank(s, 345, 195)
b.add(C, "C", "1uF", "CFLY_P", "CFLY_N")
b.add(FB, "FB", "600R@100MHz", "N5_RAW", "-5V")
r = Row(s, 330, 235)
r.add(C, "C", "1uF", "+5V", "GND")
r.add(C, "C", "1uF", "GND", "N5_RAW")
r.add(C, "C", "10uF 10V", "GNDA", "-5V")
r.add(C, "C", "100nF", "GNDA", "-5V")

s.text("PWR_FLAG (ERC icin)", 20, 245)
x = 30
for net in ("+24V", "GNDPWR", "Earth", "+5VA", "GNDA", "+15V", "-5V", "+3V3"):
    s.flag(net, x, 262)
    x += 15

# ================================================================ 2. ISLEMCI VE ETHERNET
s = P.sheet("islemci_ethernet", "2 - Islemci ve Ethernet", "A2")
mcu = {
    "PA0": "PHY_RST", "PA1": "RMII_REF_CLK", "PA2": "RMII_MDIO", "PA3": "ADC_RST", "PA4": "ADC_CS",
    "PA7": "RMII_CRS_DV", "PA8": "BTN_DEF", "PA9": "UART_TX", "PA10": "UART_RX",
    "PA13": "SWDIO", "PA14": "SWCLK", "PA15": "DAC_CS",
    "PB3": "SWO", "PB4": "LED_RUN", "PB5": "LED_ERR", "PB6": "I2C_SCL", "PB7": "I2C_SDA",
    "PB0": "DO_EN", "PB8": "DO_FAULT1", "PB9": "DO_FAULT2", "PB10": "DI_EN",
    "PB11": "RMII_TX_EN", "PB12": "RMII_TXD0", "PB13": "RMII_TXD1", "PB14": "DI_FAULT1", "PB15": "DI_FAULT2",
    "PB2": "BOOT1",
    "PC1": "RMII_MDC", "PC4": "RMII_RXD0", "PC5": "RMII_RXD1",
    "PC10": "SPI_SCK", "PC11": "SPI_MISO", "PC12": "SPI_MOSI",
    "PH0": "OSC_IN", "PH1": "OSC_OUT", "NRST": "NRST", "BOOT0": "BOOT0",
    "VDD": "+3V3", "VSS": "GND", "VBAT": "+3V3", "VDDA": "VDDA_MCU", "VREF+": "VDDA_MCU", "VSSA": "GND",
    "VCAP_1": "VCAP1", "VCAP_2": "VCAP2",
}
# PC13 kullanilmadi: akim siniri 3 mA, PhotoMOS LED'ini suremez
for i, pin in enumerate(["PC0", "PC2", "PC3", "PC6", "PC7", "PC8", "PC9", "PB1"]):
    mcu[pin] = "AI_MODE%d" % i
for i in range(16):
    mcu["PD%d" % i] = "DI%d" % i
    mcu["PE%d" % i] = "DO_CMD%d" % i
sym = kisch.libsym("MCU_ST_STM32F4:STM32F407VETx")
for p in sym.pins:
    mcu.setdefault(p.name, NC)
s.text("ISLEMCI: STM32F407VET6 (LQFP100)", 150, 22)
s.part("MCU_ST_STM32F4:STM32F407VETx", "U", "STM32F407VET6", 200, 115, mcu, refpos=(175, 32))

s.text("Islemci besleme ve yardimci devreler", 20, 205)
r = Row(s, 30, 228)
for _ in range(6):
    r.add(C, "C", "100nF", "+3V3", "GND")
r.add(C, "C", "4.7uF", "+3V3", "GND")
r.x += 8
r.add(FB, "FB", "600R@100MHz", "+3V3", "VDDA_MCU")
r.x += 8
r = Row(s, r.x, 262)
r.add(C, "C", "1uF", "VDDA_MCU", "GND")
r.add(C, "C", "100nF", "VDDA_MCU", "GND")
r.add(C, "C", "2.2uF", "VCAP1", "GND")
r.add(C, "C", "2.2uF", "VCAP2", "GND")
r.add(R, "R", "10k", "BOOT0", "GND")
r.add(R, "R", "10k", "BOOT1", "GND")
r.add(C, "C", "100nF", "NRST", "GND")
r.add(R, "R", "10k", "+3V3", "BTN_DEF")
r.add(R, "R", "10k", "DO_EN", "GND")
r.add(R, "R", "10k", "+3V3", "DI_EN")
r.add(R, "R", "10k", "+3V3", "ADC_RST")
r.add(R, "R", "10k", "+3V3", "ADC_CS")
r.add(R, "R", "10k", "+3V3", "DAC_CS")
r = Row(s, 30, 300)
r.add(R, "R", "4.7k", "+3V3", "I2C_SCL")
r.add(R, "R", "4.7k", "+3V3", "I2C_SDA")
r.add(R, "R", "1k", "+3V3", "LEDA_RUN")
r.add(R, "R", "1k", "+3V3", "LEDA_ERR")
r.add(R, "R", "1k", "+3V3", "LEDA_PWR")
r.add(C, "C", "18pF", "OSC_IN", "GND")
r.add(C, "C", "18pF", "OSC_OUT", "GND")
r.add(C, "C", "100nF", "+3V3", "GND")
b = Bank(s, 60, 335, pitch=13)
b.add(LED, "D", "RUN (yesil)", "LED_RUN", "LEDA_RUN")
b.add(LED, "D", "ERR (kirmizi)", "LED_ERR", "LEDA_ERR")
b.add("Switch:SW_Push", "SW", "RESET", "NRST", "GND")
b.add("Switch:SW_Push", "SW", "FABRIKA AYARI (5 sn)", "BTN_DEF", "GND")
r = Row(s, 130, 345)
r.add(LED, "D", "PWR (yesil)", "GND", "LEDA_PWR")
s.part("Device:Crystal_GND24", "Y", "8MHz", 185, 345,
       {"1": "OSC_IN", "3": "OSC_OUT", "2": "GND", "4": "GND"}, refpos=(193, 337))
s.part("Memory_EEPROM:24LC02", "U", "24AA02E48 (MAC + ayarlar)", 250, 340,
       {"A0": "GND", "A1": "GND", "A2": "GND", "GND": "GND", "VCC": "+3V3", "WP": "GND",
        "SDA": "I2C_SDA", "SCL": "I2C_SCL"}, refpos=(250, 326))
s.part("Connector:Conn_ARM_JTAG_SWD_10", "J", "SWD", 320, 340,
       {"VTref": "+3V3", "SWDIO/TMS": "SWDIO", "SWCLK/TCK": "SWCLK", "SWO/TDO": "SWO", "~{RESET}": "NRST",
        "GND": "GND", "GNDDetect": "GND", "KEY": NC, "NC/TDI": NC}, refpos=(305, 320))
s.part("Connector_Generic:Conn_01x03", "J", "UART (TX RX GND)", 390, 340,
       {"1": "UART_TX", "2": "UART_RX", "3": "GND"}, refpos=(392, 331))

s.text("ETHERNET: LAN8742A (RMII, 25 MHz kristal, REF_CLK Out modu) + trafolu RJ45", 330, 22)
s.part("Interface_Ethernet:LAN8742A", "U", "LAN8742A", 400, 100, {
    "VDD1A": "VDDA_PHY", "VDD2A": "VDDA_PHY", "VDDIO": "+3V3", "VDDCR": "VDDCR", "VSS": "GND",
    "TXD0": "RMII_TXD0", "TXD1": "RMII_TXD1", "TXEN": "RMII_TX_EN",
    "RXD0/MODE0": "RMII_RXD0", "RXD1/MODE1": "RMII_RXD1", "CRS_DV/MODE2": "RMII_CRS_DV",
    "RXER/PHYAD0": "PHY_RXER", "MDIO": "RMII_MDIO", "MDC": "RMII_MDC",
    "~{INT}/REFCLKO": "PHY_REFCLKO", "~{RST}": "PHY_RST",
    "XTAL1/CLKIN": "PHY_XI", "XTAL2": "PHY_XO", "RBIAS": "PHY_RBIAS",
    "LED1/REGOFF": "PHY_LED1", "LED2/~{INTSEL}": "PHY_LED2",
    "TXP": "ETH_TXP", "TXN": "ETH_TXN", "RXP": "ETH_RXP", "RXN": "ETH_RXN"}, refpos=(420, 62))
s.part("Connector:RJ45_Hanrun_HR911105A_Horizontal", "J", "HR911105A", 520, 100, {
    "TD+": "ETH_TXP", "TD-": "ETH_TXN", "RD+": "ETH_RXP", "RD-": "ETH_RXN", "TCT": "VDDA_PHY",
    "RCT": "VDDA_PHY", "NC": NC, "8": "Earth", "SH": "Earth",
    "9": "RJ_LEDG_A", "10": "GND", "12": "RJ_LEDY_A", "11": "GND"}, refpos=(520, 84))
b = Bank(s, 400, 160)
b.add(R, "R", "33R", "PHY_REFCLKO", "RMII_REF_CLK")
b.add(R, "R", "330R", "PHY_LED1", "RJ_LEDG_A")
b.add(R, "R", "330R", "PHY_LED2", "RJ_LEDY_A")
r = Row(s, 340, 200)
r.add(FB, "FB", "600R@100MHz", "+3V3", "VDDA_PHY")
r.x += 6
r = Row(s, 365, 200)
for net in ("ETH_TXP", "ETH_TXN", "ETH_RXP", "ETH_RXN"):
    r.add(R, "R", "49.9R 1%", "VDDA_PHY", net)
r.add(R, "R", "1.5k", "+3V3", "RMII_MDIO")
r.add(R, "R", "10k", "+3V3", "PHY_RST")
r = Row(s, 340, 245)
r.add(C, "C", "1uF", "VDDA_PHY", "GND")
r.add(C, "C", "100nF", "VDDA_PHY", "GND")
r.add(C, "C", "100nF", "VDDA_PHY", "GND")
r.add(C, "C", "100nF", "+3V3", "GND")
r.add(C, "C", "1uF", "VDDCR", "GND")
r.add(C, "C", "470pF", "VDDCR", "GND")
r.add(R, "R", "12.1k 1%", "PHY_RBIAS", "GND")
r.add(R, "R", "10k", "PHY_RXER", "GND")
r.add(R, "R", "10k", "PHY_LED1", "GND")
r.add(R, "R", "10k", "PHY_LED2", "GND")
r.add(C, "C", "18pF", "PHY_XI", "GND")
r.add(C, "C", "18pF", "PHY_XO", "GND")
s.part("Device:Crystal_GND24", "Y", "25MHz", 520, 250,
       {"1": "PHY_XI", "3": "PHY_XO", "2": "GND", "4": "GND"}, refpos=(528, 242))

# ================================================================ 3. DIJITAL GIRISLER
s = P.sheet("dijital_giris", "3 - Dijital girisler (16 x 24 V, sinking, IEC 61131-2 Tip 3)", "A2")
s.text("2 x ISO1228, paralel mod. RTHR = 1k, RPAR = 13k, RILIM = 0 (IL = 2.9 mA), RSURGE = 1k, "
       "CSURGE = 4.7uF, CFIL = 1nF (datasheet 8.2.1 / 8.2.4)", 20, 20)
for g in range(2):
    x0 = 20 + g * 285
    avcc = "DI_AVCC%d" % (g + 1)
    nets = {"AVCC": avcc, "AVSS": "GNDPWR", "VCC1": "+3V3", "GND1": "GND", "COMM_SEL": "GND",
            "OUT_EN": "DI_EN", "F0": "GND", "F1": "GND", "nFAULT": "DI_FAULT%d" % (g + 1), "NC": NC}
    for k in range(8):
        i = g * 8 + k
        nets["IN%d" % (k + 1)] = "DI%d_IN" % i
        nets["LED%d" % (k + 1)] = "DI%d_LED" % i
        nets["OUT%d" % (k + 1)] = "DI%d" % i
    s.part("iokart:ISO1228", "U", "ISO1228", x0 + 200, 110, nets, refpos=(x0 + 200, 82))
    term = {str(k + 1): "DI%d_T" % (g * 8 + k) for k in range(8)}
    term.update({"9": "GNDPWR", "10": "GNDPWR"})
    s.part("Connector:Screw_Terminal_01x10", "J", "DI %d-%d + 2xM" % (g * 8, g * 8 + 7), x0 + 30, 70, term,
           refpos=(x0 + 32, 52))
    b1 = Bank(s, x0 + 85, 40)
    b2 = Bank(s, x0 + 85, 110)
    for k in range(8):
        i = g * 8 + k
        b1.add(R, "R", "1k MELF", "DI%d_T" % i, "DI%d_IN" % i)
        b2.add(R, "R", "13k 1%", "DI%d_IN" % i, "DI%d_LED" % i)
    r1 = Row(s, x0 + 30, 200)
    r2 = Row(s, x0 + 30, 250)
    for k in range(8):
        i = g * 8 + k
        r1.add(LED, "D", "DI%d" % i, "GNDPWR", "DI%d_LED" % i)
        r2.add(C, "C", "1nF 50V", "DI%d_IN" % i, "GNDPWR")
    r1.x += 10
    r1.add(R, "R", "1k MELF", "+24V", avcc)
    r1.x += 6
    r1.add(C, "C", "4.7uF 50V", avcc, "GNDPWR")
    r1.add(C, "C", "1nF 50V", avcc, "GNDPWR")
    r1.x += 6
    r1.add(C, "C", "100nF", "+3V3", "GND")
    r1.add(R, "R", "4.7k", "+3V3", "DI_FAULT%d" % (g + 1))

# ================================================================ 4. DIJITAL CIKISLAR
s = P.sheet("dijital_cikis", "4 - Dijital cikislar (16 x 24 V high-side) - SURUCU ENTEGRESI EKSIK", "A2")
s.text("EKSIK: 2 x ISO8200BQ henuz cizilmedi (datasheet okunamadi, bacak tablosu dogrulanmadan eklenmedi).", 20, 20)
s.text("Hazir netler: DO_CMD0..15, DO_EN, DO_FAULT1/2 (islemci sayfasi); VDO1/VDO2, GND_DO1/GND_DO2, DO0..15 (bu sayfa).",
       20, 27)
for g in range(2):
    x0 = 20 + g * 285
    vt, v, gnd = "VDO%d_T" % (g + 1), "VDO%d" % (g + 1), "GND_DO%d" % (g + 1)
    term = {"1": vt, "10": gnd}
    term.update({str(k + 2): "DO%d" % (g * 8 + k) for k in range(8)})
    s.part("Connector:Screw_Terminal_01x10", "J", "%dL+ / DO %d-%d / %dM" % (g + 1, g * 8, g * 8 + 7, g + 1),
           x0 + 40, 75, term, refpos=(x0 + 42, 57))
    b = Bank(s, x0 + 110, 50)
    b.add(FUSE, "F", "5A", vt, v)
    b.add("Diode:SMAJ33CA", "D", "SMCJ33CA", v, gnd)
    b.add(CP, "C", "100uF 50V", v, gnd)
    b.add(C, "C", "100nF 50V", v, gnd)
    b1 = Bank(s, x0 + 110, 110)
    b2 = Bank(s, x0 + 190, 110)
    for k in range(8):
        i = g * 8 + k
        b1.add(R, "R", "10k", "DO%d" % i, "DO%d_LED" % i)
        b2.add(LED, "D", "DO%d" % i, gnd, "DO%d_LED" % i)
    s.flag(v, x0 + 190, 55)
    s.flag(gnd, x0 + 210, 55)

# ================================================================ 5. ANALOG
s = P.sheet("analog", "5 - Analog girisler (8) ve cikislar (4)", "A2")
s.text("ANALOG GIRIS: ADS8688, dahili referans. Voltaj modu +-10.24 V; akim modu 249R sont + 0-5.12 V araligi.", 20, 20)
adc = {"AVDD": "+5VA", "DVDD": "+3V3", "AGND": "GNDA", "DGND": "GND", "REFGND": "GNDA",
       "~{REFSEL}": "GNDA", "REFIO": "ADC_REFIO", "REFCAP": "ADC_REFCAP", "DAISY": "GND",
       "~{RST/PD}": "ADC_RST", "SDI": "SPI_MOSI", "SDO": "SPI_MISO", "SCLK": "SPI_SCK", "~{CS}": "ADC_CS",
       "DNC": NC, "AUX_IN": "GNDA", "AUX_GND": "GNDA"}
for i in range(8):
    adc["AIN_%dP" % i] = "AI%d_ADC" % i
    adc["AIN_%dGND" % i] = "GNDA"
adcsym = kisch.libsym("Analog_ADC:ADS8688")
adc = {k: v for k, v in adc.items() if k in {p.name for p in adcsym.pins} | {p.number for p in adcsym.pins}}
s.part("Analog_ADC:ADS8688", "U", "ADS8688", 330, 90, adc, refpos=(350, 50))
r = Row(s, 390, 80)
r.add(C, "C", "10uF", "ADC_REFIO", "GNDA")
r.add(C, "C", "10uF", "ADC_REFCAP", "GNDA")
r.add(C, "C", "1uF", "ADC_REFCAP", "GNDA")
r = Row(s, 390, 120)
r.add(C, "C", "10uF", "+5VA", "GNDA")
r.add(C, "C", "1uF", "+5VA", "GNDA")
r.add(C, "C", "1uF", "+5VA", "GNDA")
r.add(C, "C", "10uF", "+3V3", "GND")
r.add(C, "C", "100nF", "+3V3", "GND")
for g in range(2):
    term = {str(k + 1): "AI%d_T" % (g * 4 + k) for k in range(4)}
    term.update({"5": "GNDA", "6": "GNDA"})
    s.part("Connector:Screw_Terminal_01x06", "J", "AI %d-%d + 2xAGND" % (g * 4, g * 4 + 3), 35, 50 + g * 40, term,
           refpos=(37, 38 + g * 40))
for i in range(8):
    y = 40 + i * 0
    col, row = i % 4, i // 4
    x = 75 + col * 62
    y = 150 + row * 75
    s.text("AI%d" % i, x - 12, y - 14, 1.6)
    s.part("Relay_SolidState:TLP222A", "K", "TLP222A", x + 10, y,
           {"1": "AI%d_LEDA" % i, "2": "AI_MODE%d" % i, "4": "AI%d_T" % i, "3": "AI%d_SH" % i},
           refpos=(x + 10, y - 9))
    b = Bank(s, x + 10, y + 16)
    b.add(R, "R", "1k 0.1%", "AI%d_T" % i, "AI%d_ADC" % i)
    b.add(R, "R", "249R 0.1% 0.5W", "AI%d_SH" % i, "AI%d_PTC" % i)
    rr = Row(s, x - 14, y + 38, pitch=11.43)
    rr.add(R, "R", "470R", "+3V3", "AI%d_LEDA" % i)
    rr.add("Diode:SMAJ15CA", "D", "SMAJ15CA", "AI%d_T" % i, "GNDA")
    rr.add(C, "C", "10nF C0G", "AI%d_ADC" % i, "GNDA")
    rr.add(PTC, "F", "PTC 50mA", "AI%d_PTC" % i, "GNDA")

s.text("ANALOG CIKIS: DAC80504 (0-2.5 V) + OPA4197 kazanc x4 = 0-10 V. Seri direnc ve PTC geri besleme dongusunun icinde.",
       330, 180)
s.part("iokart:DAC80504", "U", "DAC80504", 360, 215,
       {"VDD": "+5VA", "VIO": "+3V3", "REF": "DAC_REF", "GAIN": "GNDA", "RSTSEL": "GNDA", "REFDIV": "GNDA",
        "LDAC": "GNDA", "GND": "GNDA", "PAD": "GNDA", "CS": "DAC_CS", "SCLK": "SPI_SCK", "SDI": "SPI_MOSI",
        "SDO": "SPI_MISO", "OUT0": "DAC_OUT0", "OUT1": "DAC_OUT1", "OUT2": "DAC_OUT2", "OUT3": "DAC_OUT3"},
       refpos=(360, 193))
r = Row(s, 420, 215)
r.add(C, "C", "220nF", "DAC_REF", "GNDA")
r.add(C, "C", "1uF", "+5VA", "GNDA")
r.add(C, "C", "100nF", "+5VA", "GNDA")
r.add(C, "C", "100nF", "+3V3", "GNDA")
r.add(C, "C", "100nF 25V", "+15V", "GNDA")
r.add(C, "C", "100nF", "GNDA", "-5V")
opref = P.ref("U")
for j in range(4):
    x = 345 + (j % 2) * 120
    y = 275 + (j // 2) * 65
    s.text("AO%d" % j, x - 12, y - 14, 1.6)
    s.part("Amplifier_Operational:OPA4197xPW", "U", "OPA4197", x, y,
           {"+": "DAC_OUT%d" % j, "-": "AO%d_FB" % j, "~": "AO%d_DRV" % j}, unit=j + 1, ref=opref,
           refpos=(x + 2, y - 8))
    b = Bank(s, x + 55, y - 8)
    b.add(R, "R", "47R", "AO%d_DRV" % j, "AO%d_P" % j)
    b.add(PTC, "F", "PTC 50mA", "AO%d_P" % j, "AO%d_T" % j)
    b.add(R, "R", "30k 0.1%", "AO%d_T" % j, "AO%d_FB" % j)
    b.add(C, "C", "100pF C0G", "AO%d_DRV" % j, "AO%d_FB" % j)
    rr = Row(s, x - 5, y + 30)
    rr.add(R, "R", "10k 0.1%", "AO%d_FB" % j, "GNDA")
    rr.add("Diode:SMAJ15CA", "D", "SMAJ15CA", "AO%d_T" % j, "GNDA")
s.part("Amplifier_Operational:OPA4197xPW", "U", "OPA4197", 560, 215, {"V+": "+15V", "V-": "-5V"}, unit=5,
       ref=opref, refpos=(568, 215))
term = {str(k + 1): "AO%d_T" % k for k in range(4)}
term.update({"5": "GNDA", "6": "GNDA"})
s.part("Connector:Screw_Terminal_01x06", "J", "AO 0-3 + 2xAGND", 560, 300, term, refpos=(562, 288))

P.write(OUT)
with open(os.path.join(OUT, "sym-lib-table"), "w") as f:
    f.write('(sym_lib_table\n  (lib (name "iokart")(type "KiCad")(uri "${KIPRJMOD}/lib/iokart.kicad_sym")'
            '(options "")(descr "IO kart ozel semboller"))\n)\n')
with open(os.path.join(OUT, "netlist_expected.txt"), "w") as f:
    for net in sorted(P.nets):
        f.write("%s: %s\n" % (net, " ".join(sorted("%s.%s" % rp for rp in P.nets[net]))))
print("sheets:", len(P.sheets), "parts:", len(P.bom), "nets:", len(P.nets))
single = sorted(n for n, v in P.nets.items() if len(v) == 1)
print("single-pin nets:", single)
