# poker-bot

Texas Hold'em poker bot that decides using odds and expected value.

## Run

Requires Python 3.

```bash
python poker_bot.py selftest
python poker_bot.py analyze --hole AsKd --board QhJc2s --pot 100 --to-call 40
python poker_bot.py simulate --hands 500 --opponent all
```

## Notes

- Chen formula preflop hand strength and a 1326-combo range table
- Pot odds, EV, MDF, GTO bluff ratio, Kelly fraction, SPR
- Bayesian-smoothed opponent stats (VPIP, PFR, aggression, fold-to-bet)
- Test opponents: Random, Calling station, Maniac, Tight-aggressive

---

Part of [Ondrej Kutlik's portfolio](https://ondrejkutlik.github.io/dev/).
