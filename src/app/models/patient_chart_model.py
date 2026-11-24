from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.hospital_model import Hospital

KST = timezone(timedelta(hours=9)) # UTC+9

class PatientChart(Base):
    __tablename__ = "patient_charts"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 환자
    hospital_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hospitals.hospital_id", ondelete="RESTRICT"), nullable=False
    )  # 병원
    chart_no: Mapped[str] = mapped_column(String(20), nullable=False)  # 차트번호 (병원 안에서 UNIQUE)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 등록 시각

    __table_args__ = (
        UniqueConstraint("hospital_id", "chart_no", name="uq_patient_charts_hospital_id_chart_no"),
    )

    # 관계
    patient: Mapped["User"] = relationship("User", back_populates="patient_charts")
    hospital: Mapped["Hospital"] = relationship("Hospital")
