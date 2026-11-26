from datetime import date, datetime, time, timedelta, timezone
from app.schema.schedule_reminder_schema import ScheduleReminderTargetDTO, ScheduleReminderRunResultDTO
from fastapi import Depends, HTTPException, status