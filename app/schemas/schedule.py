from pydantic import BaseModel


class ScheduleItem(BaseModel):
    day_of_week: int        # 0=월 ~ 6=일
    call_time: str          # "HH:MM"


class ScheduleUpdateRequest(BaseModel):
    ai_call_enabled: bool
    schedule_list: list[ScheduleItem]