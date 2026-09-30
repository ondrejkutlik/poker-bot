import argparse
import itertools
import math
import random
import statistics
import time
from collections import Counter

HODNOTY = "23456789TJQKA"
FARBY = "cdhs"
VSETKY_KARTY = list(range(52))  # Karta = hodnota (0 až 12) + 13 * farba (0 až 3)
NAZVY_RUK = ["Vysoká karta", "Pár", "Dva páry", "Trojica", "Postupka",
             "Farba", "Full house", "Štvorica", "Čistá postupka"]


def karta_text(karta):
    return HODNOTY[karta % 13] + FARBY[karta // 13]


def nacitaj_kartu(text):
    return HODNOTY.index(text[0].upper()) + 13 * FARBY.index(text[1].lower())


def nacitaj_karty(text):
    text = text.replace(" ", "").replace(",", "")
    return [nacitaj_kartu(text[i:i + 2]) for i in range(0, len(text), 2)]


def najvyssia_postupka(hodnoty):
    # Vráti najvyššiu kartu postupky alebo -1, počíta aj A-2-3-4-5
    for vrch in range(12, 3, -1):
        if all(h in hodnoty for h in range(vrch - 4, vrch + 1)):
            return vrch
    if {12, 0, 1, 2, 3} <= hodnoty:
        return 3
    return -1


def vyhodnot(karty):
    # Najlepšia 5-kartová ruka zo 5 až 7 kariet, vyššia n-tica znamená silnejšiu ruku
    pocty = Counter(k % 13 for k in karty)
    farby = Counter(k // 13 for k in karty)
    farba = next((f for f, n in farby.items() if n >= 5), None)
    vo_farbe = []
    if farba is not None:
        vo_farbe = sorted((k % 13 for k in karty if k // 13 == farba), reverse=True)
        postupka = najvyssia_postupka(set(vo_farbe))
        if postupka >= 0:
            return (8, postupka)
    skupiny = sorted(pocty.items(), key=lambda x: (x[1], x[0]), reverse=True)
    velkosti = [n for _, n in skupiny]
    if velkosti[0] == 4:
        stvorica = skupiny[0][0]
        return (7, stvorica, max(h for h in pocty if h != stvorica))
    if velkosti[0] == 3 and velkosti[1] >= 2:
        return (6, skupiny[0][0], skupiny[1][0])
    if farba is not None:
        return (5, *vo_farbe[:5])
    postupka = najvyssia_postupka(set(pocty))
    if postupka >= 0:
        return (4, postupka)
    if velkosti[0] == 3:
        kickery = sorted((h for h in pocty if h != skupiny[0][0]), reverse=True)[:2]
        return (3, skupiny[0][0], *kickery)
    if velkosti[0] == 2 and velkosti[1] == 2:
        par1, par2 = skupiny[0][0], skupiny[1][0]
        return (2, par1, par2, max(h for h in pocty if h not in (par1, par2)))
    if velkosti[0] == 2:
        kickery = sorted((h for h in pocty if h != skupiny[0][0]), reverse=True)[:3]
        return (1, skupiny[0][0], *kickery)
    return (0, *sorted(pocty, reverse=True)[:5])


def chen_skore(karta1, karta2):
    # Chenov vzorec, AA = 20 a 72o = -1
    h1, h2 = karta1 % 13, karta2 % 13
    vyssia, nizsia = max(h1, h2), min(h1, h2)

    def body(h):
        return {12: 10, 11: 8, 10: 7, 9: 6}.get(h, (h + 2) / 2)

    skore = body(vyssia)
    if vyssia == nizsia:  # Pár má dvojnásobok, minimálne 5
        return math.ceil(max(5, skore * 2))
    if karta1 // 13 == karta2 // 13:  # Suited
        skore += 2
    medzera = vyssia - nizsia - 1
    skore -= {0: 0, 1: 1, 2: 2, 3: 4}.get(medzera, 5)
    if medzera <= 1 and vyssia < 10:  # Bonus za šancu na postupku
        skore += 1
    return math.ceil(skore)


def zorad_ruky():
    kombinacie = list(itertools.combinations(range(52), 2))
    kombinacie.sort(key=lambda r: (chen_skore(*r), max(r[0] % 13, r[1] % 13),
                                   min(r[0] % 13, r[1] % 13)), reverse=True)
    return kombinacie


TABULKA_RUK = zorad_ruky()  # 1326 kombinácií od najsilnejšej


def sanca_na_outs(outs, kariet_pride, neznamych):
    # Hypergeometrické rozdelenie, šanca že príde aspoň jeden out
    if outs <= 0:
        return 0.0
    return 1 - math.comb(neznamych - outs, kariet_pride) / math.comb(neznamych, kariet_pride)


def pravidlo_4_a_2(outs, ulica):
    # Na flope outs * 4 %, na turne outs * 2 %
    return min(1.0, outs * (0.04 if ulica == 3 else 0.02))


def pot_odds(dorovnat, pot):
    # Potrebná equity na výhodný call, pot už obsahuje stávku súpera
    return dorovnat / (pot + dorovnat) if dorovnat > 0 else 0.0


def ev_call(equity, pot, dorovnat):
    return equity * pot - (1 - equity) * dorovnat


def ev_stavky(equity, pot, stavka, sanca_fold):
    return sanca_fold * pot + (1 - sanca_fold) * (equity * (pot + stavka) - (1 - equity) * stavka)


def potrebny_fold(stavka, pot):
    # Ako často musí súper zahodiť, aby bol čistý bluff na nule
    return stavka / (pot + stavka)


def mdf(stavka, pot):
    # Minimum defense frequency
    return pot / (pot + stavka)


def podiel_bluffov(stavka, pot):
    # Pri tomto podiele bluffov je súperovi jedno, či callne
    return stavka / (pot + 2 * stavka)


def kelly(p, kurz):
    # Kellyho kritérium f = (p(b+1) - 1) / b
    return max(0.0, (p * (kurz + 1) - 1) / kurz) if kurz > 0 else 0.0


def spr(stack, pot):
    return stack / pot if pot > 0 else float("inf")


def chyba_odhadu(p, n):
    return math.sqrt(p * (1 - p) / n)


# Presné počty 7-kartových rúk (zo 133 784 560 kombinácií)
POCTY_7_KARIET = {
    "Čistá postupka (aj royal)": 41_584,
    "Štvorica": 224_848,
    "Full house": 3_473_184,
    "Farba": 4_047_644,
    "Postupka": 6_180_020,
    "Trojica": 6_461_620,
    "Dva páry": 31_433_400,
    "Pár": 58_627_800,
    "Vysoká karta": 23_294_460,
}
VSETKY_7_KARIET = math.comb(52, 7)


def sance_preflop():
    spolu = math.comb(52, 2)
    return {
        "Pár (ľubovoľný)": 13 * 6 / spolu,
        "Konkrétny pár (napr. AA)": 6 / spolu,
        "Suited (obe rovnakej farby)": 4 * 78 / spolu,
        "Konkrétna suited ruka (napr. AKs)": 4 / spolu,
        "Konkrétna offsuit ruka (napr. AKo)": 12 / spolu,
        "AK (suited aj offsuit)": 16 / spolu,
        "Aspoň jedno eso": 1 - math.comb(48, 2) / spolu,
        "Dve vysoké karty (T až A)": math.comb(20, 2) / spolu,
        "Suited connectors (32s až AKs)": 4 * 12 / spolu,
    }


def pocet_outs(ruka, stol):
    # Približný počet outs na silnú ruku (postupka a vyššie) na flope a turne
    if len(stol) not in (3, 4):
        return 0
    teraz = vyhodnot(ruka + stol)
    if teraz[0] >= 4:
        return 0
    pouzite = set(ruka) | set(stol)
    outs = 0
    for karta in VSETKY_KARTY:
        if karta in pouzite:
            continue
        nova = vyhodnot(ruka + stol + [karta])
        if nova[0] < 4:
            continue
        if len(stol) == 4 and vyhodnot(stol + [karta])[0] >= nova[0]:
            continue  # Túto ruku by mal aj súper, je celá na stole
        outs += 1
    return outs


def equity_monte_carlo(ruka, stol, superi=1, simulacie=400, rozsah=None, rng=None):
    # Rozsah je podiel najsilnejších rúk, z ktorých súper hrá, None znamená hocičo
    rng = rng or random
    zname = set(ruka) | set(stol)
    najlepsie = None
    if rozsah is not None and rozsah < 0.999:
        najlepsie = TABULKA_RUK[:max(10, int(len(TABULKA_RUK) * rozsah))]
    chyba = 5 - len(stol)
    spolu = 0.0
    for _ in range(simulacie):
        pouzite = set(zname)
        ruky_superov = []
        for _ in range(superi):
            r = None
            if najlepsie is not None:
                for _ in range(25):
                    kandidat = najlepsie[rng.randrange(len(najlepsie))]
                    if kandidat[0] not in pouzite and kandidat[1] not in pouzite:
                        r = kandidat
                        break
            if r is None:
                zvysok = [k for k in VSETKY_KARTY if k not in pouzite]
                r = tuple(rng.sample(zvysok, 2))
            ruky_superov.append(r)
            pouzite.update(r)
        zvysok = [k for k in VSETKY_KARTY if k not in pouzite]
        cely_stol = stol + rng.sample(zvysok, chyba)
        moja = vyhodnot(ruka + cely_stol)
        ich = [vyhodnot(list(r) + cely_stol) for r in ruky_superov]
        najlepsia = max(ich)
        if moja > najlepsia:
            spolu += 1
        elif moja == najlepsia:
            spolu += 1 / (1 + sum(1 for x in ich if x == najlepsia))
    return spolu / simulacie


class StatistikySupera:
    # Štatistiky sú vyhladené, kým o súperovi nevieme dosť
    def __init__(self):
        self.ruky = 0
        self.vpip = 0
        self.pfr = 0
        self.agresivne = 0
        self.cally = 0
        self.proti_stavke = 0
        self.foldy_na_stavku = 0

    def vpip_podiel(self):  # Na začiatku 50 % s váhou 10 rúk
        return (self.vpip + 5) / (self.ruky + 10)

    def pfr_podiel(self):
        return (self.pfr + 2) / (self.ruky + 10)

    def agresivita(self):  # (Bety + raisy) / cally, na začiatku 1.5
        return (self.agresivne + 1.5 * 4) / (self.cally + 4)

    def fold_na_stavku(self):  # Na začiatku 40 % s váhou 5
        return (self.foldy_na_stavku + 2) / (self.proti_stavke + 5)

    def rozsah(self):
        return min(1.0, max(0.15, self.vpip_podiel()))

    def profil(self):
        tesny = "tight" if self.vpip_podiel() < 0.35 else "loose"
        if self.agresivita() > 2:
            styl = "aggressive"
        elif self.agresivita() < 1:
            styl = "passive"
        else:
            styl = "balanced"
        return f"{tesny}-{styl}"


class Hrac:
    meno = "Hráč"

    def nova_ruka(self):
        pass

    def pozoruj(self, ulica, akcia, proti_stavke):
        pass

    def tah(self, s):
        raise NotImplementedError


UPRAVA_POZICIE = {"skora": -0.02, "stredna": 0.0, "neskora": 0.02}


class PokerBot(Hrac):
    meno = "MC-EV Bot"

    def __init__(self, simulacie=400, seed=None, bluff=1.0):
        self.simulacie = simulacie
        self.rng = random.Random(seed)
        self.bluff = bluff
        self.protihrac = StatistikySupera()
        self.posledne = {}
        self.vpip_zapocitany = self.pfr_zapocitany = False

    def nova_ruka(self):
        self.protihrac.ruky += 1
        self.vpip_zapocitany = self.pfr_zapocitany = False

    def pozoruj(self, ulica, akcia, proti_stavke):
        o = self.protihrac
        if ulica == 0:
            if akcia in ("call", "raise") and not self.vpip_zapocitany:
                o.vpip += 1
                self.vpip_zapocitany = True
            if akcia == "raise" and not self.pfr_zapocitany:
                o.pfr += 1
                self.pfr_zapocitany = True
        else:
            if akcia == "raise":
                o.agresivne += 1
            elif akcia == "call":
                o.cally += 1
            if proti_stavke:
                o.proti_stavke += 1
                if akcia == "fold":
                    o.foldy_na_stavku += 1

    def rozsah_supera(self, s):
        rozsah = self.protihrac.rozsah()
        if s["dorovnat"] > 0:
            velkost = min(s["dorovnat"] / max(s["pot"] - s["dorovnat"], 1), 1.5)
            zuzenie = min(0.6, 0.3 * velkost / (0.5 + self.protihrac.agresivita()))
            if s["stol"] == []:
                zuzenie = max(zuzenie, 0.35)  # Raise pred flopom znamená užší rozsah
            rozsah *= (1 - zuzenie)
        return max(0.08, rozsah)

    def raise_na(self, s, cast_potu):
        ciel = s["moja_stavka"] + s["dorovnat"] + cast_potu * (s["pot"] + s["dorovnat"])
        return self.obmedz(s, ciel)

    @staticmethod
    def obmedz(s, ciel):
        suma = int(round(max(s["min_raise"], min(ciel, s["max_raise"]))))
        if suma > 0.6 * s["max_raise"]:  # Nenechávam si zbytočne malý zvyšok stacku
            suma = s["max_raise"]
        return suma

    def tah(self, s):
        ruka, stol = s["ruka"], s["stol"]
        ulica = len(stol)
        rozsah = self.rozsah_supera(s)
        eq = equity_monte_carlo(ruka, stol, s["superi"], self.simulacie, rozsah, self.rng)
        eq = min(1.0, max(0.0, eq + UPRAVA_POZICIE[s["pozicia"]]))
        po = pot_odds(s["dorovnat"], s["pot"])
        self.posledne = {
            "equity": eq, "pot_odds": po, "rozsah": rozsah, "ulica": ulica,
            "ev_call": ev_call(eq, s["pot"], s["dorovnat"]),
            "spr": spr(s["stack"], s["pot"]), "profil": self.protihrac.profil(),
        }
        if ulica == 0:
            akcia = self.pred_flopom(s, eq, po)
        else:
            akcia = self.po_flope(s, eq, po)
        self.posledne["akcia"] = akcia
        return akcia

    def pred_flopom(self, s, eq, po):
        bb, dorovnat = s["bb"], s["dorovnat"]
        stavka = s["moja_stavka"] + dorovnat
        chen = chen_skore(*s["ruka"])
        self.posledne["chen"] = chen
        hranica = {"skora": 9, "stredna": 8, "neskora": 5}[s["pozicia"]]

        if stavka <= bb:  # Nikto nezvýšil
            if chen >= hranica or eq > 0.62:
                velkost = 3.0 if s["pozicia"] != "neskora" else 2.5
                return ("raise", self.obmedz(s, velkost * bb))
            if dorovnat == 0:
                return ("check", 0)
            return ("call", 0) if eq > po + 0.03 else ("fold", 0)

        # Súper zvýšil
        if stavka >= 8 * bb:  # 3-bet a viac
            if chen >= 14 or eq > 0.70:
                return ("raise", s["max_raise"])
            return ("call", 0) if eq > po + 0.05 and chen >= 10 else ("fold", 0)
        if chen >= 11 or eq > 0.60:
            return ("raise", self.obmedz(s, 3 * stavka))  # 3-bet
        if eq > po + 0.04 and chen >= 7:
            return ("call", 0)
        return ("fold", 0)

    def po_flope(self, s, eq, po):
        ulica = len(s["stol"])
        superi = s["superi"]
        outs = pocet_outs(s["ruka"], s["stol"])
        self.posledne["outs"] = outs
        nahoda = self.rng.random()
        ferova = 1 / (superi + 1)
        nizke_spr = self.posledne["spr"] < 3

        if s["dorovnat"] == 0:  # Nikto nestavil
            naskok = eq - ferova
            if naskok > 0.30:
                return ("raise", self.raise_na(s, 0.75))
            if naskok > 0.15:
                return ("raise", self.raise_na(s, 0.60))
            if naskok > 0.05 and nahoda < 0.5:
                return ("raise", self.raise_na(s, 0.33))  # Tenká value stávka
            if outs >= 8 and ulica < 5 and nahoda < 0.55 * self.bluff:
                return ("raise", self.raise_na(s, 0.50))  # Semi-bluff
            if (eq < 0.30 and superi == 1 and self.protihrac.fold_na_stavku() > 0.42
                    and nahoda < podiel_bluffov(0.66, 1.0) * self.bluff):
                return ("raise", self.raise_na(s, 0.66))  # Čistý bluff
            return ("check", 0)

        # Súper stavil
        potrebna = po
        if self.protihrac.agresivita() > 2.0:
            potrebna -= 0.03  # Agresívny súper bluffuje častejšie
        if outs >= 8 and ulica < 5:
            potrebna *= 0.9  # Implied odds
        if s["stack"] - s["dorovnat"] < 0.25 * (s["pot"] + s["dorovnat"]):
            potrebna -= 0.03
        self.posledne["potrebna_equity"] = potrebna
        if eq > max(0.75, potrebna + 0.25):
            if nizke_spr:
                return ("raise", s["max_raise"])
            return ("raise", self.raise_na(s, 1.0))
        if eq - potrebna > 0.02:
            return ("call", 0)
        if outs >= 12 and ulica < 5 and nahoda < 0.4 * self.bluff:
            return ("raise", self.raise_na(s, 1.0))  # Semi-bluff s veľa outs
        return ("fold", 0)


class NahodnyHrac(Hrac):
    meno = "Náhodný"

    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def tah(self, s):
        r = self.rng.random()
        if s["dorovnat"] > 0:
            if r < 0.25:
                return ("fold", 0)
            if r < 0.80:
                return ("call", 0)
        elif r < 0.70:
            return ("check", 0)
        return ("raise", int(s["moja_stavka"] + s["dorovnat"] + 0.5 * s["pot"]))


class CallingStation(Hrac):
    meno = "Calling station"

    def tah(self, s):
        return ("call", 0) if s["dorovnat"] > 0 else ("check", 0)


class Maniak(Hrac):
    meno = "Maniak"

    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def tah(self, s):
        if self.rng.random() < 0.7:
            return ("raise", int(s["moja_stavka"] + s["dorovnat"] + s["pot"] + s["dorovnat"]))
        return ("call", 0) if s["dorovnat"] > 0 else ("check", 0)


class TightAgresivny(Hrac):
    meno = "Tight-aggressive"

    def __init__(self, seed=None, simulacie=120):
        self.rng = random.Random(seed)
        self.simulacie = simulacie

    def tah(self, s):
        bb = s["bb"]
        if not s["stol"]:
            chen = chen_skore(*s["ruka"])
            if s["moja_stavka"] + s["dorovnat"] > 4 * bb:
                return ("call", 0) if chen >= 12 else ("fold", 0)
            if chen >= 8:
                return ("raise", int(3 * bb))
            if s["dorovnat"] == 0:
                return ("check", 0)
            return ("call", 0) if chen >= 5 else ("fold", 0)
        eq = equity_monte_carlo(s["ruka"], s["stol"], 1, self.simulacie, None, self.rng)
        po = pot_odds(s["dorovnat"], s["pot"])
        if eq > 0.62:
            return ("raise", int(s["moja_stavka"] + s["dorovnat"] + 0.66 * (s["pot"] + s["dorovnat"])))
        if s["dorovnat"] == 0:
            return ("check", 0)
        return ("call", 0) if eq > po + 0.03 else ("fold", 0)


def odohraj_ruku(hraci, button, bb, stack_na_zaciatku, rng, max_raisov=4):
    # Jedna ruka heads-up, vráti zisk hráča 0 v žetónoch
    balicek = VSETKY_KARTY[:]
    rng.shuffle(balicek)
    ruky = [balicek[0:2], balicek[2:4]]
    cely_stol = balicek[4:9]
    stack = [stack_na_zaciatku, stack_na_zaciatku]
    vlozene = [0, 0]
    sb, bb_hrac = button, 1 - button
    for h in hraci:
        h.nova_ruka()

    def zaplat(i, suma):
        suma = int(min(suma, stack[i]))
        stack[i] -= suma
        vlozene[i] += suma
        return suma

    zahodil = None
    for ulica, kariet in enumerate((0, 3, 4, 5)):
        stol = cely_stol[:kariet]
        stavky = [0, 0]
        if ulica == 0:
            stavky[sb] = zaplat(sb, bb // 2)
            stavky[bb_hrac] = zaplat(bb_hrac, bb)
            prvy = sb
        else:
            prvy = bb_hrac
        aktualna, posledne_zvysenie, raisy = max(stavky), bb, 0
        na_rade = [prvy, 1 - prvy]
        while na_rade:
            i = na_rade.pop(0)
            dorovnat = aktualna - stavky[i]
            if stack[i] == 0 or (stack[1 - i] == 0 and dorovnat == 0):
                continue
            maximum = stavky[i] + stack[i]
            s = {
                "ruka": ruky[i], "stol": stol, "pot": sum(vlozene),
                "dorovnat": min(dorovnat, stack[i]), "stack": stack[i],
                "moja_stavka": stavky[i], "bb": bb, "superi": 1,
                "min_raise": min(aktualna + posledne_zvysenie, maximum), "max_raise": maximum,
                "pozicia": "neskora" if i == button else "skora",
            }
            akcia, suma = hraci[i].tah(s)
            moze_zvysit = raisy < max_raisov and stack[i] > dorovnat and stack[1 - i] > 0
            if akcia == "raise" and not moze_zvysit:
                akcia = "call" if dorovnat > 0 else "check"
            if akcia == "fold" and dorovnat == 0:
                akcia = "check"
            hraci[1 - i].pozoruj(ulica, akcia, dorovnat > 0)
            if akcia == "fold":
                zahodil = i
                break
            if akcia in ("call", "check"):
                stavky[i] += zaplat(i, dorovnat)
                continue
            raise_na = int(max(min(aktualna + posledne_zvysenie, maximum), min(suma, maximum)))
            stavky[i] += zaplat(i, raise_na - stavky[i])
            if raise_na - aktualna >= posledne_zvysenie:
                posledne_zvysenie = raise_na - aktualna
            aktualna = raise_na
            raisy += 1
            na_rade = [1 - i]
        if zahodil is not None:
            break

    if zahodil is not None:
        stack[1 - zahodil] += sum(vlozene)
    else:
        navyse = vlozene[0] - vlozene[1]  # Vrátim časť stávky, ktorú nikto nedorovnal
        if navyse > 0:
            stack[0] += navyse
            vlozene[0] -= navyse
        elif navyse < 0:
            stack[1] += -navyse
            vlozene[1] += navyse
        pot = sum(vlozene)
        prva, druha = vyhodnot(ruky[0] + cely_stol), vyhodnot(ruky[1] + cely_stol)
        if prva > druha:
            stack[0] += pot
        elif druha > prva:
            stack[1] += pot
        else:
            stack[0] += pot // 2
            stack[1] += pot - pot // 2
    return stack[0] - stack_na_zaciatku


def simuluj(hrdina, protihrac, pocet_ruk, seed=1, bb=2, stack_v_bb=100):
    rng = random.Random(seed)
    vysledky = []
    for r in range(pocet_ruk):
        vysledky.append(odohraj_ruku([hrdina, protihrac], r % 2, bb, stack_v_bb * bb, rng) / bb)
    priemer = statistics.fmean(vysledky)
    chyba = statistics.stdev(vysledky) / math.sqrt(len(vysledky)) if len(vysledky) > 1 else 0.0
    return {
        "ruky": pocet_ruk, "bb_100": priemer * 100, "chyba_bb_100": chyba * 100,
        "vyhry": sum(v > 0 for v in vysledky) / pocet_ruk, "spolu_bb": sum(vysledky),
    }


def test():
    def e(text):
        return vyhodnot(nacitaj_karty(text))

    assert e("AsKsQsJsTs2c3d")[0] == 8
    assert e("2c3d4h5s6cKdQd")[0] == 4 and e("Ac2d3h4s5cKdQd") == (4, 3)
    assert e("AsAdAhAc2c3d4h")[0] == 7
    assert e("AsAdAhKcKd2c3d")[0] == 6
    assert e("2s5s9sJsKs3c4d")[0] == 5
    assert e("AsAd2c2d3h5s9c")[0] == 2
    assert e("AsAdKcQd3h5s9c")[0] == 1
    assert e("AsKdQc9d3h5s2c")[0] == 0
    assert e("AsAdKcQd3h5s9c") > e("AhAcKsJd3d5c9h")  # Rozhodne kicker
    assert sum(POCTY_7_KARIET.values()) == VSETKY_7_KARIET
    assert chen_skore(nacitaj_kartu("As"), nacitaj_kartu("Ad")) == 20
    assert chen_skore(nacitaj_kartu("As"), nacitaj_kartu("Ks")) == 12
    assert chen_skore(nacitaj_kartu("7s"), nacitaj_kartu("2d")) == -1
    eq = equity_monte_carlo(nacitaj_karty("AsAd"), [], 1, 4000, None, random.Random(1))
    assert 0.82 < eq < 0.88, eq
    assert abs(sanca_na_outs(9, 2, 47) - 0.3497) < 1e-3
    assert abs(pot_odds(50, 150) - 0.25) < 1e-9
    print("Všetky testy prešli.")


def analyza(args):
    ruka = nacitaj_karty(args.ruka)
    stol = nacitaj_karty(args.stol) if args.stol else []
    superi = args.superi
    ulica = len(stol)
    eq = equity_monte_carlo(ruka, stol, superi, args.simulacie, None, random.Random(7))
    print(f"Ruka: {' '.join(map(karta_text, ruka))}   Stôl: {' '.join(map(karta_text, stol)) or '-'}")
    if len(ruka + stol) >= 5:
        print(f"Aktuálna ruka: {NAZVY_RUK[vyhodnot(ruka + stol)[0]]}")
    if ulica == 0:
        print(f"Chen skóre: {chen_skore(*ruka)}")
    print(f"Equity proti {superi} náhodným súperom: {eq:.1%}  (+-{chyba_odhadu(eq, args.simulacie):.1%})")
    outs = pocet_outs(ruka, stol)
    if outs:
        neznamych = 52 - len(ruka) - len(stol)
        pride = 2 if ulica == 3 else 1
        print(f"Outs (postupka a vyššie): {outs}, šanca dotiahnuť: "
              f"{sanca_na_outs(outs, pride, neznamych):.1%} (pravidlo 4 a 2: {pravidlo_4_a_2(outs, ulica):.0%})")
    if args.dorovnat > 0:
        po = pot_odds(args.dorovnat, args.pot)
        print(f"Pot odds: {po:.1%} | EV callu: {ev_call(eq, args.pot, args.dorovnat):+.1f} | "
              f"MDF: {mdf(args.dorovnat, args.pot - args.dorovnat):.1%}")
        print("Odporúčanie:", "CALL alebo RAISE" if eq > po else "FOLD")
    else:
        print(f"Kellyho kritérium (len informačne, 1:1): {kelly(eq, 1.0):.1%}")


def spusti_simulaciu(args):
    superi = {"nahodny": NahodnyHrac, "station": CallingStation, "maniak": Maniak,
              "tag": TightAgresivny}
    vybrani = list(superi) if args.super == "vsetci" else [args.super]
    print(f"{'Súper':<18}{'ruky':>6}{'bb/100':>10}{'+-chyba':>9}{'výhry':>8}{'čas':>8}")
    for nazov in vybrani:
        hrdina = PokerBot(simulacie=args.simulacie, seed=args.seed)
        protihrac = superi[nazov](seed=args.seed + 1) if nazov != "station" else CallingStation()
        zaciatok = time.time()
        v = simuluj(hrdina, protihrac, args.ruky, seed=args.seed)
        print(f"{protihrac.meno:<18}{v['ruky']:>6}{v['bb_100']:>10.1f}{v['chyba_bb_100']:>9.1f}"
              f"{v['vyhry']:>8.1%}{time.time() - zaciatok:>7.0f}s   [{hrdina.protihrac.profil()}]")


def main():
    parser = argparse.ArgumentParser(description="Texas Hold'em bot")
    prikazy = parser.add_subparsers(dest="prikaz", required=True)
    prikazy.add_parser("test")
    a = prikazy.add_parser("analyza")
    a.add_argument("--ruka", required=True)
    a.add_argument("--stol", default="")
    a.add_argument("--pot", type=float, default=0)
    a.add_argument("--dorovnat", type=float, default=0)
    a.add_argument("--superi", type=int, default=1)
    a.add_argument("--simulacie", type=int, default=5000)
    s = prikazy.add_parser("simulacia")
    s.add_argument("--ruky", type=int, default=500)
    s.add_argument("--simulacie", type=int, default=200)
    s.add_argument("--super", default="vsetci",
                   choices=["vsetci", "nahodny", "station", "maniak", "tag"])
    s.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    if args.prikaz == "test":
        test()
    elif args.prikaz == "analyza":
        analyza(args)
    else:
        spusti_simulaciu(args)


if __name__ == "__main__":
    main()
