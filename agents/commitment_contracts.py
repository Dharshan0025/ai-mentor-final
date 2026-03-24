"""
Commitment Contracts — Students set study goals and track progress.
Increases accountability and learning outcomes.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum
from db import db

logger = logging.getLogger(__name__)


class CommitmentStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CommitmentContract:
    """Represents a student's commitment contract."""

    def __init__(
        self,
        student_id: str,
        commitment: str,
        target_date: str,
        frequency: str = "daily",  # daily, weekly, once
        goal_metric: str = "",  # e.g., "solve 5 problems", "master OS topic"
    ):
        self.student_id = student_id
        self.commitment = commitment
        self.target_date = datetime.fromisoformat(target_date)
        self.frequency = frequency
        self.goal_metric = goal_metric
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.progress = 0  # 0-100
        self.check_ins = []  # List of check-in records
        self.status = CommitmentStatus.ACTIVE

    def add_check_in(self, progress_update: int, notes: str = ""):
        """Record a check-in (progress update)."""
        check_in = {
            "timestamp": datetime.now().isoformat(),
            "progress": progress_update,
            "notes": notes,
        }
        self.check_ins.append(check_in)
        self.progress = min(100, max(self.progress, progress_update))
        self.updated_at = datetime.now()

        logger.info(f"✅ Check-in recorded: {self.commitment[:40]}... ({progress_update}%)")
        return check_in

    def complete(self):
        """Mark commitment as completed."""
        self.status = CommitmentStatus.COMPLETED
        self.progress = 100
        self.updated_at = datetime.now()
        logger.info(f"🎉 Commitment completed: {self.commitment}")

    def fail(self):
        """Mark commitment as failed."""
        self.status = CommitmentStatus.FAILED
        self.updated_at = datetime.now()
        logger.info(f"❌ Commitment failed: {self.commitment}")

    def is_due_soon(self, hours: int = 24) -> bool:
        """Check if commitment is due within N hours."""
        return 0 <= (self.target_date - datetime.now()).total_seconds() < hours * 3600

    def is_overdue(self) -> bool:
        """Check if commitment is overdue."""
        return datetime.now() > self.target_date and self.status == CommitmentStatus.ACTIVE

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "student_id": self.student_id,
            "commitment": self.commitment,
            "target_date": self.target_date.isoformat(),
            "frequency": self.frequency,
            "goal_metric": self.goal_metric,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "progress": self.progress,
            "check_ins": self.check_ins,
            "status": self.status.value,
            "is_overdue": self.is_overdue(),
            "days_remaining": max(0, (self.target_date - datetime.now()).days),
        }


class CommitmentManager:
    """Manage all commitment contracts for a student."""

    def __init__(self, student_id: str):
        self.student_id = student_id
        self.contracts: List[CommitmentContract] = []

    async def create_contract(
        self,
        commitment: str,
        target_date: str,
        frequency: str = "daily",
        goal_metric: str = "",
    ) -> CommitmentContract:
        """Create a new commitment contract."""
        contract = CommitmentContract(
            student_id=self.student_id,
            commitment=commitment,
            target_date=target_date,
            frequency=frequency,
            goal_metric=goal_metric,
        )
        self.contracts.append(contract)

        # Save to database
        if hasattr(db, "save_commitment_contract"):
            try:
                await db.save_commitment_contract(contract.to_dict())
                logger.info(f"💾 Commitment contract saved: {commitment[:40]}...")
            except Exception as e:
                logger.warning(f"Failed to save commitment: {e}")

        return contract

    async def load_contracts(self) -> List[CommitmentContract]:
        """Load active commitments from database."""
        if not hasattr(db, "get_active_commitments"):
            return self.contracts

        try:
            contract_data = await db.get_active_commitments(self.student_id)
            self.contracts = [
                CommitmentContract(
                    student_id=c["student_id"],
                    commitment=c["commitment"],
                    target_date=c["target_date"],
                    frequency=c.get("frequency", "daily"),
                    goal_metric=c.get("goal_metric", ""),
                )
                for c in (contract_data or [])
            ]
            logger.info(f"✅ Loaded {len(self.contracts)} active commitments for {self.student_id}")
        except Exception as e:
            logger.warning(f"Failed to load commitments: {e}")

        return self.contracts

    async def get_active_contracts(self) -> List[CommitmentContract]:
        """Get all active (not completed/failed/cancelled) contracts."""
        return [c for c in self.contracts if c.status == CommitmentStatus.ACTIVE]

    async def get_overdue_contracts(self) -> List[CommitmentContract]:
        """Get overdue contracts that need attention."""
        return [c for c in await self.get_active_contracts() if c.is_overdue()]

    async def get_upcoming_contracts(self, hours: int = 24) -> List[CommitmentContract]:
        """Get contracts due within N hours."""
        return [c for c in await self.get_active_contracts() if c.is_due_soon(hours)]

    async def check_in_on_commitment(
        self,
        commitment_text: str,
        progress: int,
        notes: str = ""
    ) -> Optional[dict]:
        """Record progress on a commitment."""
        for contract in self.contracts:
            if commitment_text.lower() in contract.commitment.lower():
                check_in = contract.add_check_in(progress, notes)

                # Auto-complete if 100%
                if progress >= 100:
                    contract.complete()

                # Save to database
                if hasattr(db, "save_commitment_check_in"):
                    try:
                        await db.save_commitment_check_in(
                            student_id=self.student_id,
                            commitment=commitment_text,
                            check_in=check_in,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to save check-in: {e}")

                return check_in

        return None

    def get_summary(self) -> dict:
        """Get summary of commitment contracts."""
        active = [c for c in self.contracts if c.status == CommitmentStatus.ACTIVE]
        completed = [c for c in self.contracts if c.status == CommitmentStatus.COMPLETED]
        failed = [c for c in self.contracts if c.status == CommitmentStatus.FAILED]

        avg_progress = (
            sum(c.progress for c in active) / len(active)
            if active
            else 0
        )

        return {
            "total_commitments": len(self.contracts),
            "active": len(active),
            "completed": len(completed),
            "failed": len(failed),
            "completion_rate": f"{(len(completed) / max(len(self.contracts), 1) * 100):.0f}%",
            "avg_progress": f"{avg_progress:.0f}%",
            "overdue": len([c for c in active if c.is_overdue()]),
            "due_soon": len([c for c in active if c.is_due_soon()]),
            "contracts": [c.to_dict() for c in self.contracts[:5]],  # Last 5
        }


# Global cache of commitment managers
_commitment_managers: dict[str, CommitmentManager] = {}


def get_commitment_manager(student_id: str) -> CommitmentManager:
    """Get or create commitment manager for a student."""
    if student_id not in _commitment_managers:
        _commitment_managers[student_id] = CommitmentManager(student_id)
    return _commitment_managers[student_id]


async def send_commitment_reminders():
    """Background task to send reminders for upcoming commitments."""
    for student_id, manager in _commitment_managers.items():
        upcoming = await manager.get_upcoming_contracts(hours=24)
        overdue = await manager.get_overdue_contracts()

        if upcoming:
            logger.info(f"📬 Upcoming reminders for {student_id}: {len(upcoming)} commitments")
            # TODO: Send push notification / email

        if overdue:
            logger.info(f"⚠️ Overdue reminders for {student_id}: {len(overdue)} commitments")
            # TODO: Send urgent reminder
