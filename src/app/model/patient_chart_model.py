from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.hospital_model import Hospital

KST = timezone(timedelta(hours=9)) # UTC+9

# 환자 차트번호
class PatientChart(Base):
    __tablename__ = "patient_charts"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hospital_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False, index=True
    )
    chart_no: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    __table_args__ = (
        UniqueConstraint("hospital_id", "chart_no", name="uq_patient_charts_hospital_id_chart_no"),
        UniqueConstraint("patient_id", "hospital_id", name="uq_patient_charts_patient_id_hospital_id"),
    )

    # 관계
    patient: Mapped["User"] = relationship("User", back_populates="patient_charts")
    hospital: Mapped["Hospital"] = relationship("Hospital", back_populates="patient_charts")
