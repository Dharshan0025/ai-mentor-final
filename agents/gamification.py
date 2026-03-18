"""
Gamification Agent — Phase 4 V6 Classroom Experience
======================================================

Manages XP, levels, streaks, and badges for students.

XP Earn Rules:
  lesson_complete    → +50 XP  (+ bloom_level * 10 bonus)
  checkpoint_pass    → +20 XP
  first_checkpoint   → +30 XP  (first correct in session)
  streak_3           → +25 XP  (3-day study streak)
  streak_7           → +75 XP  (7-day streak)
  streak_30          → +200 XP (30-day streak)
  badge_earned       → +100 XP

Level thresholds: level = floor(total_xp / 100) + 1 (capped at 50)

Badge catalog (triggered by milestones):
  first_lesson       → "First Steps" 🌱           (1 lesson completed)
  quiz_ace           → "Quiz Ace" ⚡              (10 checkpoints passed)
  streak_hero        → "Streak Hero" 🔥           (7-day streak)
  bloom_master       → "Bloom Master" 🧠          (Bloom level ≥ 5)
  comeback           → "Comeback Kid" 💪          (lesson after 7-day gap)
  level_5            → "Rising Scholar" 📚        (level 5)
  level_10           → "Knowledge Seeker" 🔭      (level 10)
  level_25           → "Academic Champion" 🏆     (level 25)
"""
import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── XP amounts per action ──────────────────────────────────────────────────────
XP_TABLE = {
    "lesson_complete":    50,
    "checkpoint_pass":    20,
    "first_checkpoint":   30,
    "streak_3":           25,
    "streak_7":           75,
    "streak_30":         200,
    "badge_earned":      100,
    "exam_complete":      40,
    "exam_perfect":      150,  # 100% exam score
}

# ── Badge definitions ──────────────────────────────────────────────────────────
BADGES = {
    "first_lesson":    {"name": "First Steps",         "icon": "🌱", "desc": "Complete your first lesson"},
    "quiz_ace":        {"name": "Quiz Ace",            "icon": "⚡", "desc": "Pass 10 checkpoint questions"},
    "streak_hero":     {"name": "Streak Hero",         "icon": "🔥", "desc": "Study 7 days in a row"},
    "bloom_master":    {"name": "Bloom Master",        "icon": "🧠", "desc": "Reach Bloom level 5 in any subject"},
    "comeback":        {"name": "Comeback Kid",        "icon": "💪", "desc": "Return after a 7-day break"},
    "level_5":         {"name": "Rising Scholar",      "icon": "📚", "desc": "Reach Level 5"},
    "level_10":        {"name": "Knowledge Seeker",    "icon": "🔭", "desc": "Reach Level 10"},
    "level_25":        {"name": "Academic Champion",   "icon": "🏆", "desc": "Reach Level 25"},
    "perfect_exam":    {"name": "Perfect Score",       "icon": "🎯", "desc": "Score 100% on an exam"},
    "speed_learner":   {"name": "Speed Learner",       "icon": "⚡", "desc": "Complete a lesson in under 10 minutes"},
}


def xp_to_level(total_xp: int) -> int:
    return min(50, (total_xp // 100) + 1)


def level_progress_pct(total_xp: int) -> float:
    """Progress towards next level (0.0–1.0)."""
    xp_in_level = total_xp % 100
    return round(xp_in_level / 100, 3)


class GamificationAgent:
    """Handles all XP/badge operations. Requires an async DB pool passed in."""

    def __init__(self, pool):
        self.pool = pool

    async def award_xp(
        self,
        *,
        student_db_id: int,
        action: str,
        amount: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Award XP for an action. Updates student_xp + inserts into xp_ledger.
        Returns { total_xp, level, xp_gained, badges_earned }.
        """
        xp_gained = amount if amount is not None else XP_TABLE.get(action, 10)
        if xp_gained <= 0:
            return {"total_xp": 0, "level": 1, "xp_gained": 0, "badges_earned": []}

        today = date.today()
        badges_earned = []

        async with self.pool.acquire() as conn:
            # Upsert student_xp
            row = await conn.fetchrow(
                """
                INSERT INTO student_xp (student_db_id, total_xp, level, streak_days, last_activity, updated_at)
                VALUES ($1, $2, $3, 1, $4, NOW())
                ON CONFLICT (student_db_id) DO UPDATE
                  SET total_xp    = student_xp.total_xp + $2,
                      level       = LEAST(50, (student_xp.total_xp + $2) / 100 + 1),
                      streak_days = CASE
                        WHEN student_xp.last_activity = $4 - 1 THEN student_xp.streak_days + 1
                        WHEN student_xp.last_activity = $4      THEN student_xp.streak_days
                        ELSE 1
                      END,
                      last_activity = $4,
                      updated_at  = NOW()
                RETURNING total_xp, level, streak_days, last_activity
                """,
                student_db_id, xp_gained, xp_to_level(xp_gained), today,
            )

            total_xp    = row["total_xp"]
            level       = row["level"]
            streak_days = row["streak_days"]
            last_act    = row["last_activity"]

            # Log to ledger
            await conn.execute(
                "INSERT INTO xp_ledger (student_db_id, action, amount, metadata) VALUES ($1, $2, $3, $4)",
                student_db_id, action, xp_gained, metadata,
            )

            # Check streak XP bonuses
            streak_action = None
            if streak_days == 3:
                streak_action = "streak_3"
            elif streak_days == 7:
                streak_action = "streak_7"
            elif streak_days == 30:
                streak_action = "streak_30"

            if streak_action:
                bonus = XP_TABLE[streak_action]
                await conn.execute(
                    "UPDATE student_xp SET total_xp = total_xp + $1, updated_at = NOW() WHERE student_db_id = $2",
                    bonus, student_db_id,
                )
                await conn.execute(
                    "INSERT INTO xp_ledger (student_db_id, action, amount) VALUES ($1, $2, $3)",
                    student_db_id, streak_action, bonus,
                )
                total_xp += bonus

            # Check badge unlocks
            badges_earned = await self._check_and_award_badges(
                conn,
                student_db_id=student_db_id,
                total_xp=total_xp,
                level=level,
                streak_days=streak_days,
                action=action,
                metadata=metadata or {},
            )

        return {
            "total_xp":     total_xp,
            "level":        level,
            "xp_gained":    xp_gained,
            "streak_days":  streak_days,
            "level_progress": level_progress_pct(total_xp),
            "badges_earned": badges_earned,
        }

    async def _check_and_award_badges(
        self,
        conn,
        *,
        student_db_id: int,
        total_xp: int,
        level: int,
        streak_days: int,
        action: str,
        metadata: dict,
    ) -> list[dict]:
        """Check all badge conditions and award any newly earned badges."""
        earned = []

        async def _award(badge_id: str) -> bool:
            b = BADGES[badge_id]
            try:
                await conn.execute(
                    """INSERT INTO student_badges (student_db_id, badge_id, badge_name, badge_icon, description)
                       VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING""",
                    student_db_id, badge_id, b["name"], b["icon"], b["desc"],
                )
                # Award bonus XP for badge
                await conn.execute(
                    "UPDATE student_xp SET total_xp = total_xp + $1, updated_at = NOW() WHERE student_db_id = $2",
                    XP_TABLE["badge_earned"], student_db_id,
                )
                earned.append({"badge_id": badge_id, **b})
                return True
            except Exception:
                return False

        # Count lessons and checkpoints for badge checks
        counts = await conn.fetchrow(
            """
            SELECT
              (SELECT COUNT(*) FROM xp_ledger WHERE student_db_id=$1 AND action='lesson_complete') AS lessons,
              (SELECT COUNT(*) FROM xp_ledger WHERE student_db_id=$1 AND action='checkpoint_pass') AS checkpoints
            """,
            student_db_id,
        )
        lessons    = int(counts["lessons"] or 0)
        checks     = int(counts["checkpoints"] or 0)

        # Badge checks
        if lessons >= 1:                    await _award("first_lesson")
        if checks >= 10:                    await _award("quiz_ace")
        if streak_days >= 7:                await _award("streak_hero")
        if level >= 5:                      await _award("level_5")
        if level >= 10:                     await _award("level_10")
        if level >= 25:                     await _award("level_25")
        if action == "exam_perfect":        await _award("perfect_exam")
        if metadata.get("bloom_level", 0) >= 5: await _award("bloom_master")

        return earned

    async def get_xp_summary(self, student_db_id: int) -> dict:
        """
        Full XP + badge summary for a student.
        Returns { total_xp, level, streak_days, level_progress, badges, recent_ledger }.
        """
        async with self.pool.acquire() as conn:
            xp_row = await conn.fetchrow(
                "SELECT total_xp, level, streak_days, last_activity FROM student_xp WHERE student_db_id=$1",
                student_db_id,
            )
            badges = await conn.fetch(
                "SELECT badge_id, badge_name, badge_icon, description, earned_at FROM student_badges WHERE student_db_id=$1 ORDER BY earned_at DESC",
                student_db_id,
            )
            ledger = await conn.fetch(
                "SELECT action, amount, created_at FROM xp_ledger WHERE student_db_id=$1 ORDER BY created_at DESC LIMIT 20",
                student_db_id,
            )

        if not xp_row:
            return {
                "total_xp": 0, "level": 1, "streak_days": 0,
                "level_progress": 0.0, "badges": [], "recent_ledger": [],
            }

        total_xp = int(xp_row["total_xp"])
        return {
            "total_xp":       total_xp,
            "level":          int(xp_row["level"]),
            "streak_days":    int(xp_row["streak_days"]),
            "last_activity":  str(xp_row["last_activity"] or ""),
            "level_progress": level_progress_pct(total_xp),
            "xp_to_next_level": 100 - (total_xp % 100),
            "badges": [
                {
                    "badge_id":   b["badge_id"],
                    "name":       b["badge_name"],
                    "icon":       b["badge_icon"],
                    "description": b["description"],
                    "earned_at":  str(b["earned_at"]),
                }
                for b in badges
            ],
            "recent_ledger": [
                {"action": l["action"], "amount": l["amount"], "at": str(l["created_at"])}
                for l in ledger
            ],
        }


# ── Singleton factory ──────────────────────────────────────────────────────────
_gamification: Optional[GamificationAgent] = None


async def get_gamification_agent() -> GamificationAgent:
    global _gamification
    if _gamification is None:
        from db import get_pool
        pool = await get_pool()
        _gamification = GamificationAgent(pool)
    return _gamification
