"""
Bulk esports prediction engine for backtest calibration.

Makes systematic predictions based on esports domain knowledge:
tier list rankings, recent tournament results, and team strength assessment.
"""
from __future__ import annotations

# Tier 1 Dota 2 team strength ratings (approx May 2026 context)
# Based on TI13, recent LAN results, and overall competitive landscape
DOTA2_TIER: dict[str, float] = {
    # Tier S (0.85-0.95) — reigning champions, consistent top 2
    "Team Spirit": 0.92,
    "Team Liquid": 0.90,
    # Tier 1 (0.78-0.85) — consistent top 4-6
    "Tundra Esports": 0.82,
    "Team Falcons": 0.80,
    "BetBoom Team": 0.78,
    "PARIVISION": 0.78,
    "Xtreme Gaming": 0.80,
    # Tier 1.5 (0.68-0.75) — top regional teams, occasional international threat
    "OG": 0.72,
    "Aurora": 0.68,
    "LGD Gaming": 0.65,
    # Tier 2 (0.50-0.62) — newer/unproven teams
    "GLYPH": 0.52,
    "Team Yandex": 0.50,
}

# Tier 1 League of Legends team strength ratings (approx Spring/Summer 2026)
LOL_TIER: dict[str, float] = {
    # LCK (Korea)
    "T1": 0.90,
    "Gen.G": 0.88,
    "Hanwha Life Esports": 0.82,
    "Dplus KIA": 0.72,
    "KT Rolster": 0.68,
    "DRX": 0.60,
    "FearX": 0.52,
    "NS RedForce": 0.50,
    "BRO": 0.42,
    # LPL (China)
    "Bilibili Gaming": 0.85,
    "JD Gaming": 0.80,
    "Top Esports": 0.78,
    "Weibo Gaming": 0.70,
    "Invictus Gaming": 0.65,
    "Anyone's Legend": 0.58,
    "LNG Esports": 0.68,
    # LEC (Europe)
    "G2 Esports": 0.78,
    "Fnatic": 0.72,
    "MAD Lions KOI": 0.65,
    "Team BDS": 0.62,
    "SK Gaming": 0.55,
    "Team Heretics": 0.52,
    "GIANTX": 0.50,
    "Rogue": 0.55,
    "Karmine Corp": 0.58,
    "Team Vitality": 0.60,
    # LCS/LTA (Americas)
    "Cloud9": 0.65,
    "Team Liquid Honda": 0.62,
    "100 Thieves": 0.58,
    "FlyQuest": 0.60,
    "Dignitas": 0.50,
    "Immortals": 0.45,
    "Shopify Rebellion": 0.48,
}

# Tier 1 Valorant team strength ratings (approx 2026)
VALORANT_TIER: dict[str, float] = {
    # VCT Americas
    "Sentinels": 0.82,
    "LOUD": 0.78,
    "Leviatán": 0.75,
    "G2 Esports": 0.72,
    "100 Thieves": 0.68,
    "Cloud9": 0.65,
    "KRÜ Esports": 0.55,
    "NRG": 0.62,
    "FURIA": 0.58,
    "Evil Geniuses": 0.70,
    # VCT EMEA
    "Fnatic": 0.78,
    "Team Heretics": 0.72,
    "FUT Esports": 0.68,
    "Team Vitality": 0.65,
    "Natus Vincere": 0.70,
    "BBL Esports": 0.52,
    "KOI": 0.55,
    # VCT Pacific
    "DRX": 0.75,
    "Paper Rex": 0.72,
    "Gen.G": 0.68,
    "T1": 0.65,
    "Talon Esports": 0.60,
    "ZETA DIVISION": 0.55,
    "Global Esports": 0.48,
    "Rex Regum Qeon": 0.52,
}

CS2_TIER: dict[str, float] = {
    # Tier S
    "Team Spirit": 0.88,
    "G2": 0.85,
    "FaZe Clan": 0.82,
    "Natus Vincere": 0.85,
    "MOUZ": 0.80,
    "Team Vitality": 0.82,
    # Tier 1
    "Heroic": 0.72,
    "Eternal Fire": 0.68,
    "FURIA": 0.65,
    "Cloud9": 0.62,
    "Complexity": 0.58,
    "Astralis": 0.60,
    "Virtus.pro": 0.65,
    "BIG": 0.58,
    "Ninjas in Pyjamas": 0.55,
    "fnatic": 0.52,
    "3DMAX": 0.50,
    "SAW": 0.52,
    "Falcons": 0.50,
}

GAME_TIERS = {
    "dota2": DOTA2_TIER,
    "league-of-legends": LOL_TIER,
    "valorant": VALORANT_TIER,
    "cs2": CS2_TIER,
}


def predict_esports_match(
    game: str,
    team_a: str,
    team_b: str,
) -> dict:
    """Predict the winner of an esports match using domain knowledge.

    Uses team strength tier lists. When a team is unknown, assigns
    a default 0.50 rating and marks low confidence.

    Returns a dict with prediction fields matching the backtest format.
    """
    tier_map = GAME_TIERS.get(game, {})
    rating_a = tier_map.get(team_a)
    rating_b = tier_map.get(team_b)

    # Both known
    if rating_a is not None and rating_b is not None:
        # Elo-style win probability using logistic function
        import math
        diff = rating_a - rating_b
        prob_a = 1.0 / (1.0 + math.exp(-diff * 8))  # scale factor for esports
        prob_b = 1.0 - prob_a

        if prob_a > prob_b:
            winner = team_a
        else:
            winner = team_b

        # Confidence based on rating gap
        gap = abs(diff)
        if gap > 0.20:
            confidence = "high"
        elif gap > 0.10:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "predicted_winner": winner,
            "team_a_probability": round(prob_a, 2),
            "team_b_probability": round(prob_b, 2),
            "confidence": confidence,
            "abstain": False,
        }

    # One unknown
    if rating_a is not None:
        prob_a = 0.70
        prob_b = 0.30
        return {
            "predicted_winner": team_a,
            "team_a_probability": prob_a,
            "team_b_probability": prob_b,
            "confidence": "low",
            "abstain": False,
        }
    if rating_b is not None:
        prob_a = 0.30
        prob_b = 0.70
        return {
            "predicted_winner": team_b,
            "team_a_probability": prob_a,
            "team_b_probability": prob_b,
            "confidence": "low",
            "abstain": False,
        }

    # Both unknown — default to abstain
    return {
        "predicted_winner": "abstain",
        "team_a_probability": 0.50,
        "team_b_probability": 0.50,
        "confidence": "low",
        "abstain": True,
    }
