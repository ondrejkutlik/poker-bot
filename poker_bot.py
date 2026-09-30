#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import math
import random
import statistics
import time
from collections import Counter
from dataclasses import dataclass

RANKS = "23456789TJQKA"
SUITS = "cdhs"
ALL_CARDS = list(range(52))          # karta = rank (0..12) + 13 * farba (0..3)
HAND_NAMES = ["High card", "Pair", "Two pair", "Three of a kind", "Straight",
              "Flush", "Full house", "Four of a kind", "Straight flush"]


def card_str(c: int) -> str:
    return RANKS[c % 13] + SUITS[c // 13]


def parse_card(s: str) -> int:
    return RANKS.index(s[0].upper()) + 13 * SUITS.index(s[1].lower())


def parse_cards(s: str) -> list[int]:
    s = s.replace(" ", "").replace(",", "")
    return [parse_card(s[i:i + 2]) for i in range(0, len(s), 2)]


def _straight_high(rank_set: set[int]) -> int:
    """Najvyssia karta strita alebo -1. Podporuje wheel (A-2-3-4-5)."""
    for high in range(12, 3, -1):
        if all(r in rank_set for r in range(high - 4, high + 1)):
            return high
    if {12, 0, 1, 2, 3} <= rank_set:
        return 3
    return -1


def evaluate(cards: list[int]) -> tuple:
    """Najlepsia 5-kartova ruka z 5-7 kariet. Vyssia n-tica = silnejsia ruka."""
    rc = Counter(c % 13 for c in cards)
    sc = Counter(c // 13 for c in cards)
    flush_suit = next((s for s, n in sc.items() if n >= 5), None)
    fr: list[int] = []
    if flush_suit is not None:
        fr = sorted((c % 13 for c in cards if c // 13 == flush_suit), reverse=True)
        sf = _straight_high(set(fr))
        if sf >= 0:
            return (8, sf)
    groups = sorted(rc.items(), key=lambda x: (x[1], x[0]), reverse=True)
    counts = [n for _, n in groups]
    if counts[0] == 4:
        quad = groups[0][0]
        return (7, quad, max(r for r in rc if r != quad))
    if counts[0] == 3 and counts[1] >= 2:
        return (6, groups[0][0], groups[1][0])
    if flush_suit is not None:
        return (5, *fr[:5])
    sh = _straight_high(set(rc))
    if sh >= 0:
        return (4, sh)
    if counts[0] == 3:
        kick = sorted((r for r in rc if r != groups[0][0]), reverse=True)[:2]
        return (3, groups[0][0], *kick)
    if counts[0] == 2 and counts[1] == 2:
        p1, p2 = groups[0][0], groups[1][0]
        return (2, p1, p2, max(r for r in rc if r not in (p1, p2)))
    if counts[0] == 2:
        kick = sorted((r for r in rc if r != groups[0][0]), reverse=True)[:3]
        return (1, groups[0][0], *kick)
    return (0, *sorted(rc, reverse=True)[:5])


def chen_score(c1: int, c2: int) -> int:
    """Chenov vzorec: AA = 20, 72o = -1. Rychle odhadne silu startovej ruky."""
    r1, r2 = c1 % 13, c2 % 13
    hi, lo = max(r1, r2), min(r1, r2)

    def pts(r: int) -> float:
        return {12: 10, 11: 8, 10: 7, 9: 6}.get(r, (r + 2) / 2)

    score = pts(hi)
    if hi == lo:                                  # par: dvojnasobok, minimum 5
        return math.ceil(max(5, score * 2))
    if c1 // 13 == c2 // 13:                      # suited
        score += 2
    gap = hi - lo - 1
    score -= {0: 0, 1: 1, 2: 2, 3: 4}.get(gap, 5)
    if gap <= 1 and hi < 10:                      # bonus za straight potencial
        score += 1
    return math.ceil(score)


def _build_range_table() -> list[tuple[int, int]]:
    combos = list(itertools.combinations(range(52), 2))
    combos.sort(key=lambda h: (chen_score(*h), max(h[0] % 13, h[1] % 13),
                               min(h[0] % 13, h[1] % 13)), reverse=True)
    return combos


RANGE_TABLE = _build_range_table()               # 1326 kombinacii od najsilnejsej


def prob_hit_outs(outs: int, cards_to_come: int, unseen: int) -> float:
    """Hypergeometricke rozdelenie: P(aspon jeden out prisiel)."""
    if outs <= 0:
        return 0.0
    return 1 - math.comb(unseen - outs, cards_to_come) / math.comb(unseen, cards_to_come)


def rule_of_4_and_2(outs: int, street: int) -> float:
    """Pravidlo 4 a 2: flop (2 karty do rivera) -> outs*4 %, turn -> outs*2 %."""
    return min(1.0, outs * (0.04 if street == 3 else 0.02))


def pot_odds(to_call: float, pot: float) -> float:
    """Potrebna equity na profitabilny call. `pot` uz obsahuje supernovu stavku."""
    return to_call / (pot + to_call) if to_call > 0 else 0.0


def ev_call(equity: float, pot: float, to_call: float) -> float:
    return equity * pot - (1 - equity) * to_call


def ev_bet(equity: float, pot: float, bet: float, fold_freq: float) -> float:
    """EV stavky so 'fold equity': super zahodi s pravdepodobnostou fold_freq."""
    return fold_freq * pot + (1 - fold_freq) * (equity * (pot + bet) - (1 - equity) * bet)


def breakeven_fold_freq(bet: float, pot: float) -> float:
    """Ako casto musi super zahodit, aby cisty bluff bol EV = 0."""
    return bet / (pot + bet)


def mdf(bet: float, pot: float) -> float:
    """Minimum Defense Frequency: aspon takto casto treba brnit ruku proti stavke."""
    return pot / (pot + bet)


def gto_bluff_ratio(bet: float, pot: float) -> float:
    """Podiel bluffov v stavkovom rozsahu, pri ktorom je super indiferentny k callu."""
    return bet / (pot + 2 * bet)


def kelly_fraction(p: float, net_odds: float) -> float:
    """Kellyho kriterium: f* = (p(b+1) - 1) / b  (informativny udaj o riziku)."""
    return max(0.0, (p * (net_odds + 1) - 1) / net_odds) if net_odds > 0 else 0.0


def spr(stack: float, pot: float) -> float:
    """Stack-to-Pot Ratio: nizke SPR (<3) = pot commitment."""
    return stack / pot if pot > 0 else float("inf")


def mc_standard_error(p: float, n: int) -> float:
    return math.sqrt(p * (1 - p) / n)


# Presne pocty 7-kartovych ruk (z 133 784 560 kombinacii)
SEVEN_CARD_COUNTS = {
    "Straight flush (vratane royal)": 41_584,
    "Four of a kind": 224_848,
    "Full house": 3_473_184,
    "Flush": 4_047_644,
    "Straight": 6_180_020,
    "Three of a kind": 6_461_620,
    "Two pair": 31_433_400,
    "Pair": 58_627_800,
    "High card": 23_294_460,
}
SEVEN_CARD_TOTAL = math.comb(52, 7)


def preflop_combo_probabilities() -> dict[str, float]:
    total = math.comb(52, 2)
    return {
        "Pocket pair (lubovolny)": 13 * 6 / total,
        "Konkretny par (napr. AA)": 6 / total,
        "Suited (obe rovnakej farby)": 4 * 78 / total,
        "Konkretna suited ruka (napr. AKs)": 4 / total,
        "Konkretna offsuit ruka (napr. AKo)": 12 / total,
        "AK (suited aj offsuit)": 16 / total,
        "Aspon jedno eso": 1 - math.comb(48, 2) / total,
        "Dve broadway karty (T-A)": math.comb(20, 2) / total,
        "Suited connectors (32s az AKs)": 4 * 12 / total,
    }


def draw_outs(hole: list[int], board: list[int]) -> int:
    """Priblizny pocet outs na silnu ruku (straight+) na flope/turne."""
    if len(board) not in (3, 4):
        return 0
    cur = evaluate(hole + board)
    if cur[0] >= 4:
        return 0
    used = set(hole) | set(board)
    outs = 0
    for c in ALL_CARDS:
        if c in used:
            continue
        new = evaluate(hole + board + [c])
        if new[0] < 4:
            continue
        if len(board) == 4 and evaluate(board + [c])[0] >= new[0]:
            continue        # ruku by mal aj super z boardu, nie z nasich kariet
        outs += 1
    return outs


def monte_carlo_equity(hole: list[int], board: list[int], n_opp: int = 1,
                       sims: int = 400, opp_range_pct: float | None = None,
                       rng: random.Random | None = None) -> float:
    rng = rng or random
    known = set(hole) | set(board)
    top = None
    if opp_range_pct is not None and opp_range_pct < 0.999:
        top = RANGE_TABLE[:max(10, int(len(RANGE_TABLE) * opp_range_pct))]
    need = 5 - len(board)
    total = 0.0
    for _ in range(sims):
        used = set(known)
        opps = []
        for _ in range(n_opp):
            h = None
            if top is not None:
                for _ in range(25):
                    cand = top[rng.randrange(len(top))]
                    if cand[0] not in used and cand[1] not in used:
                        h = cand
                        break
            if h is None:
                pool = [c for c in ALL_CARDS if c not in used]
                h = tuple(rng.sample(pool, 2))
            opps.append(h)
            used.update(h)
        pool = [c for c in ALL_CARDS if c not in used]
        full = board + rng.sample(pool, need)
        mine = evaluate(hole + full)
        scores = [evaluate(list(h) + full) for h in opps]
        best = max(scores)
        if mine > best:
            total += 1
        elif mine == best:
            total += 1 / (1 + sum(1 for s in scores if s == best))
    return total / sims


@dataclass
class OpponentStats:
    """Bayesovsky vyhladene statistiky: VPIP, PFR, agresivita, fold-to-bet."""
    hands: int = 0
    vpip: int = 0
    pfr: int = 0
    aggr_actions: int = 0
    calls: int = 0
    faced_bet: int = 0
    folds_to_bet: int = 0

    def vpip_pct(self) -> float:           # prior 50 % s vahou 10 ruk
        return (self.vpip + 5) / (self.hands + 10)

    def pfr_pct(self) -> float:
        return (self.pfr + 2) / (self.hands + 10)

    def aggression(self) -> float:         # AF = (bety+raisy)/cally, prior 1.5
        return (self.aggr_actions + 1.5 * 4) / (self.calls + 4)

    def fold_to_bet(self) -> float:        # prior 40 % s vahou 5
        return (self.folds_to_bet + 2) / (self.faced_bet + 5)

    def range_pct(self) -> float:
        return min(1.0, max(0.15, self.vpip_pct()))

    def profile(self) -> str:
        tight = "tight" if self.vpip_pct() < 0.35 else "loose"
        style = "aggressive" if self.aggression() > 2 else "passive" if self.aggression() < 1 else "balanced"
        return f"{tight}-{style}"


class BasePlayer:
    name = "base"

    def new_hand(self) -> None: ...
    def observe(self, street: int, action: str, faced_bet: bool) -> None: ...
    def act(self, s: dict) -> tuple[str, int]:
        raise NotImplementedError


POSITION_ADJ = {"early": -0.02, "middle": 0.0, "late": 0.02}


class PokerBot(BasePlayer):
    name = "MC-EV Bot"

    def __init__(self, sims: int = 400, seed: int | None = None, bluff_scale: float = 1.0):
        self.sims = sims
        self.rng = random.Random(seed)
        self.bluff_scale = bluff_scale
        self.opp = OpponentStats()
        self.last: dict = {}
        self._vpip_done = self._pfr_done = False

    def new_hand(self) -> None:
        self.opp.hands += 1
        self._vpip_done = self._pfr_done = False

    def observe(self, street: int, action: str, faced_bet: bool) -> None:
        o = self.opp
        if street == 0:
            if action in ("call", "raise") and not self._vpip_done:
                o.vpip += 1
                self._vpip_done = True
            if action == "raise" and not self._pfr_done:
                o.pfr += 1
                self._pfr_done = True
        else:
            if action == "raise":
                o.aggr_actions += 1
            elif action == "call":
                o.calls += 1
            if faced_bet:
                o.faced_bet += 1
                if action == "fold":
                    o.folds_to_bet += 1

    def _opp_range(self, s: dict) -> float:
        base = self.opp.range_pct()
        if s["to_call"] > 0:
            bet_frac = min(s["to_call"] / max(s["pot"] - s["to_call"], 1), 1.5)
            shrink = min(0.6, 0.3 * bet_frac / (0.5 + self.opp.aggression()))
            if s["board"] == []:
                shrink = max(shrink, 0.35)       # preflop raise = uzsi rozsah
            base *= (1 - shrink)
        return max(0.08, base)

    def _raise_to(self, s: dict, frac: float) -> int:
        """Raise na `frac` velkosti potu (po vyrovnani)."""
        target = s["my_bet"] + s["to_call"] + frac * (s["pot"] + s["to_call"])
        return self._clamp(s, target)

    @staticmethod
    def _clamp(s: dict, target: float) -> int:
        t = int(round(max(s["min_raise_to"], min(target, s["max_raise_to"]))))
        if t > 0.6 * s["max_raise_to"]:          # vyhni sa nezmyselnemu zvysku stacku
            t = s["max_raise_to"]
        return t

    def act(self, s: dict) -> tuple[str, int]:
        hole, board = s["hole"], s["board"]
        street = len(board)
        rng_pct = self._opp_range(s)
        eq = monte_carlo_equity(hole, board, s["n_opponents"], self.sims, rng_pct, self.rng)
        eq = min(1.0, max(0.0, eq + POSITION_ADJ[s["position"]]))
        po = pot_odds(s["to_call"], s["pot"])
        self.last = dict(equity=eq, pot_odds=po, opp_range=rng_pct, street=street,
                         ev_call=ev_call(eq, s["pot"], s["to_call"]),
                         spr=spr(s["stack"], s["pot"]), opp_profile=self.opp.profile())
        if street == 0:
            action = self._preflop(s, eq, po)
        else:
            action = self._postflop(s, eq, po)
        self.last["action"] = action
        return action

    def _preflop(self, s: dict, eq: float, po: float) -> tuple[str, int]:
        bb, to_call = s["bb"], s["to_call"]
        cur_bet = s["my_bet"] + to_call
        chen = chen_score(*s["hole"])
        self.last["chen"] = chen
        open_thr = {"early": 9, "middle": 8, "late": 5}[s["position"]]

        if cur_bet <= bb:                                    # nezvysena hra
            if chen >= open_thr or eq > 0.62:
                size = 3.0 if s["position"] != "late" else 2.5
                return ("raise", self._clamp(s, size * bb))
            if to_call == 0:
                return ("check", 0)
            return ("call", 0) if eq > po + 0.03 else ("fold", 0)

        # cielim na raise
        if cur_bet >= 8 * bb:                                # 3-bet+ pot
            if chen >= 14 or eq > 0.70:
                return ("raise", s["max_raise_to"])
            return ("call", 0) if eq > po + 0.05 and chen >= 10 else ("fold", 0)
        if chen >= 11 or eq > 0.60:
            return ("raise", self._clamp(s, 3 * cur_bet))    # 3-bet
        if eq > po + 0.04 and chen >= 7:
            return ("call", 0)
        return ("fold", 0)

    def _postflop(self, s: dict, eq: float, po: float) -> tuple[str, int]:
        street = len(s["board"])
        n_opp = s["n_opponents"]
        outs = draw_outs(s["hole"], s["board"])
        self.last["outs"] = outs
        rnd = self.rng.random()
        fair = 1 / (n_opp + 1)
        low_spr = self.last["spr"] < 3

        if s["to_call"] == 0:                                # nikto nestavil
            edge = eq - fair
            if edge > 0.30:
                return ("raise", self._raise_to(s, 0.75))
            if edge > 0.15:
                return ("raise", self._raise_to(s, 0.60))
            if edge > 0.05 and rnd < 0.5:
                return ("raise", self._raise_to(s, 0.33))    # tenky value / ochrana
            if outs >= 8 and street < 5 and rnd < 0.55 * self.bluff_scale:
                return ("raise", self._raise_to(s, 0.50))    # semi-bluff
            if (eq < 0.30 and n_opp == 1 and self.opp.fold_to_bet() > 0.42
                    and rnd < gto_bluff_ratio(0.66, 1.0) * self.bluff_scale):
                return ("raise", self._raise_to(s, 0.66))    # cisty bluff
            return ("check", 0)

        # cielim na stavku
        req = po
        if self.opp.aggression() > 2.0:
            req -= 0.03                                      # agresivny super blufuje viac
        if outs >= 8 and street < 5:
            req *= 0.9                                       # implied odds
        committed = s["stack"] - s["to_call"] < 0.25 * (s["pot"] + s["to_call"])
        if committed:
            req -= 0.03
        self.last["required_equity"] = req
        if eq > max(0.75, req + 0.25):
            if low_spr:
                return ("raise", s["max_raise_to"])
            return ("raise", self._raise_to(s, 1.0))         # value raise
        if eq - req > 0.02:
            return ("call", 0)
        if outs >= 12 and street < 5 and rnd < 0.4 * self.bluff_scale:
            return ("raise", self._raise_to(s, 1.0))         # semi-bluff raise (combo draw)
        return ("fold", 0)


class RandomBot(BasePlayer):
    name = "Random"

    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def act(self, s):
        r = self.rng.random()
        if s["to_call"] > 0:
            if r < 0.25:
                return ("fold", 0)
            if r < 0.80:
                return ("call", 0)
        elif r < 0.70:
            return ("check", 0)
        return ("raise", int(s["my_bet"] + s["to_call"] + 0.5 * s["pot"]))


class CallingStation(BasePlayer):
    name = "Calling station"

    def act(self, s):
        return ("call", 0) if s["to_call"] > 0 else ("check", 0)


class Maniac(BasePlayer):
    name = "Maniac"

    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def act(self, s):
        if self.rng.random() < 0.7:
            return ("raise", int(s["my_bet"] + s["to_call"] + s["pot"] + s["to_call"]))
        return ("call", 0) if s["to_call"] > 0 else ("check", 0)


class TightAggressive(BasePlayer):
    name = "Tight-aggressive"

    def __init__(self, seed=None, sims=120):
        self.rng = random.Random(seed)
        self.sims = sims

    def act(self, s):
        bb = s["bb"]
        if not s["board"]:
            chen = chen_score(*s["hole"])
            if s["my_bet"] + s["to_call"] > 4 * bb:
                return ("call", 0) if chen >= 12 else ("fold", 0)
            if chen >= 8:
                return ("raise", int(3 * bb))
            if s["to_call"] == 0:
                return ("check", 0)
            return ("call", 0) if chen >= 5 else ("fold", 0)
        eq = monte_carlo_equity(s["hole"], s["board"], 1, self.sims, None, self.rng)
        po = pot_odds(s["to_call"], s["pot"])
        if eq > 0.62:
            return ("raise", int(s["my_bet"] + s["to_call"] + 0.66 * (s["pot"] + s["to_call"])))
        if s["to_call"] == 0:
            return ("check", 0)
        return ("call", 0) if eq > po + 0.03 else ("fold", 0)


def play_hand(players: list[BasePlayer], button: int, bb: int, start_stack: int,
              rng: random.Random, max_raises: int = 4) -> int:
    """Odohra jednu ruku heads-up. Vracia zisk hraca 0 v zetonoch."""
    deck = ALL_CARDS[:]
    rng.shuffle(deck)
    holes = [deck[0:2], deck[2:4]]
    full_board = deck[4:9]
    stack = [start_stack, start_stack]
    contrib = [0, 0]
    sb_i, bb_i = button, 1 - button
    for p in players:
        p.new_hand()

    def pay(i, amt):
        amt = int(min(amt, stack[i]))
        stack[i] -= amt
        contrib[i] += amt
        return amt

    folded = None
    for street, n_board in enumerate((0, 3, 4, 5)):
        board = full_board[:n_board]
        street_bet = [0, 0]
        if street == 0:
            street_bet[sb_i] = pay(sb_i, bb // 2)
            street_bet[bb_i] = pay(bb_i, bb)
            first = sb_i
        else:
            first = bb_i
        cur, last_inc, raises = max(street_bet), bb, 0
        pending = [first, 1 - first]
        while pending:
            i = pending.pop(0)
            to_call = cur - street_bet[i]
            if stack[i] == 0 or (stack[1 - i] == 0 and to_call == 0):
                continue
            max_to = street_bet[i] + stack[i]
            s = dict(hole=holes[i], board=board, pot=sum(contrib), to_call=min(to_call, stack[i]),
                     stack=stack[i], my_bet=street_bet[i], bb=bb, n_opponents=1,
                     min_raise_to=min(cur + last_inc, max_to), max_raise_to=max_to,
                     position="late" if i == button else "early")
            action, amt = players[i].act(s)
            can_raise = raises < max_raises and stack[i] > to_call and stack[1 - i] > 0
            if action == "raise" and not can_raise:
                action = "call" if to_call > 0 else "check"
            if action == "fold" and to_call == 0:
                action = "check"
            players[1 - i].observe(street, action, to_call > 0)
            if action == "fold":
                folded = i
                break
            if action in ("call", "check"):
                street_bet[i] += pay(i, to_call)
                continue
            raise_to = int(max(min(cur + last_inc, max_to), min(amt, max_to)))
            street_bet[i] += pay(i, raise_to - street_bet[i])
            if raise_to - cur >= last_inc:
                last_inc = raise_to - cur
            cur = raise_to
            raises += 1
            pending = [1 - i]
        if folded is not None:
            break

    if folded is not None:
        winner = 1 - folded
        stack[winner] += sum(contrib)
    else:
        over = contrib[0] - contrib[1]                   # vrat neodpovedany prebytok
        if over > 0:
            stack[0] += over; contrib[0] -= over
        elif over < 0:
            stack[1] += -over; contrib[1] += over
        pot = sum(contrib)
        s0, s1 = evaluate(holes[0] + full_board), evaluate(holes[1] + full_board)
        if s0 > s1:
            stack[0] += pot
        elif s1 > s0:
            stack[1] += pot
        else:
            stack[0] += pot // 2; stack[1] += pot - pot // 2
    return stack[0] - start_stack


def simulate(hero: BasePlayer, villain: BasePlayer, hands: int, seed: int = 1,
             bb: int = 2, start_bb: int = 100) -> dict:
    rng = random.Random(seed)
    results = []
    for h in range(hands):
        results.append(play_hand([hero, villain], h % 2, bb, start_bb * bb, rng) / bb)
    mean = statistics.fmean(results)
    se = statistics.stdev(results) / math.sqrt(len(results)) if len(results) > 1 else 0.0
    return dict(hands=hands, bb_per_100=mean * 100, se_bb_per_100=se * 100,
                win_rate=sum(r > 0 for r in results) / hands, total_bb=sum(results))


def self_test() -> None:
    e = lambda s: evaluate(parse_cards(s))
    assert e("AsKsQsJsTs2c3d")[0] == 8
    assert e("2c3d4h5s6cKdQd")[0] == 4 and e("Ac2d3h4s5cKdQd") == (4, 3)
    assert e("AsAdAhAc2c3d4h")[0] == 7
    assert e("AsAdAhKcKd2c3d")[0] == 6
    assert e("2s5s9sJsKs3c4d")[0] == 5
    assert e("AsAd2c2d3h5s9c")[0] == 2
    assert e("AsAdKcQd3h5s9c")[0] == 1
    assert e("AsKdQc9d3h5s2c")[0] == 0
    assert e("AsAdKcQd3h5s9c") > e("AhAcKsJd3d5c9h")            # kicker
    assert sum(SEVEN_CARD_COUNTS.values()) == SEVEN_CARD_TOTAL
    assert chen_score(parse_card("As"), parse_card("Ad")) == 20
    assert chen_score(parse_card("As"), parse_card("Ks")) == 12
    assert chen_score(parse_card("7s"), parse_card("2d")) == -1
    eq = monte_carlo_equity(parse_cards("AsAd"), [], 1, 4000, None, random.Random(1))
    assert 0.82 < eq < 0.88, eq
    assert abs(prob_hit_outs(9, 2, 47) - 0.3497) < 1e-3
    assert abs(pot_odds(50, 150) - 0.25) < 1e-9
    print("Vsetky testy presli.")


def analyze(args) -> None:
    hole, board = parse_cards(args.hole), parse_cards(args.board) if args.board else []
    n_opp = args.opponents
    street = len(board)
    eq = monte_carlo_equity(hole, board, n_opp, args.sims, None, random.Random(7))
    print(f"Ruka: {' '.join(map(card_str, hole))}   Board: {' '.join(map(card_str, board)) or '-'}")
    if len(hole + board) >= 5:
        print(f"Aktualna ruka: {HAND_NAMES[evaluate(hole + board)[0]]}")
    if street == 0:
        print(f"Chen score: {chen_score(*hole)}")
    print(f"Equity proti {n_opp} nahodnym supernikom: {eq:.1%}  (+-{mc_standard_error(eq, args.sims):.1%})")
    outs = draw_outs(hole, board)
    if outs:
        unseen = 52 - len(hole) - len(board)
        to_come = 2 if street == 3 else 1
        print(f"Outs (straight+): {outs} -> sanca dotiahnut: {prob_hit_outs(outs, to_come, unseen):.1%}"
              f" (pravidlo 4/2: {rule_of_4_and_2(outs, street):.0%})")
    if args.to_call > 0:
        po = pot_odds(args.to_call, args.pot)
        print(f"Pot odds: {po:.1%} | EV(call) = {ev_call(eq, args.pot, args.to_call):+.1f} | "
              f"MDF = {mdf(args.to_call, args.pot - args.to_call):.1%}")
        print("Odporucanie:", "CALL/RAISE" if eq > po else "FOLD")
    else:
        print(f"Kelly fraction (informativne, 1:1): {kelly_fraction(eq, 1.0):.1%}")


def run_simulation(args) -> None:
    opponents = {"random": RandomBot, "station": CallingStation, "maniac": Maniac,
                 "tag": TightAggressive}
    chosen = list(opponents) if args.opponent == "all" else [args.opponent]
    print(f"{'Super':<18}{'ruky':>6}{'bb/100':>10}{'+-SE':>8}{'win%':>8}{'cas':>8}")
    for name in chosen:
        hero = PokerBot(sims=args.sims, seed=args.seed)
        villain = opponents[name](seed=args.seed + 1) if name != "station" else CallingStation()
        t = time.time()
        r = simulate(hero, villain, args.hands, seed=args.seed)
        print(f"{villain.name:<18}{r['hands']:>6}{r['bb_per_100']:>10.1f}{r['se_bb_per_100']:>8.1f}"
              f"{r['win_rate']:>8.1%}{time.time() - t:>7.0f}s   [{hero.opp.profile()}]")


def main() -> None:
    ap = argparse.ArgumentParser(description="Texas Hold'em bot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    a = sub.add_parser("analyze")
    a.add_argument("--hole", required=True)
    a.add_argument("--board", default="")
    a.add_argument("--pot", type=float, default=0)
    a.add_argument("--to-call", type=float, default=0)
    a.add_argument("--opponents", type=int, default=1)
    a.add_argument("--sims", type=int, default=5000)
    s = sub.add_parser("simulate")
    s.add_argument("--hands", type=int, default=500)
    s.add_argument("--sims", type=int, default=200)
    s.add_argument("--opponent", default="all", choices=["all", "random", "station", "maniac", "tag"])
    s.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    {"selftest": lambda: self_test(), "analyze": lambda: analyze(args),
     "simulate": lambda: run_simulation(args)}[args.cmd]()


if __name__ == "__main__":
    main()
