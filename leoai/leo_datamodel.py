
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from typing import List, Optional
from pydantic import BaseModel, HttpUrl
from datetime import datetime, timezone
from enum import Enum


DEFAULT_TEMPERATURE_SCORE = 0.68

# Data models
class Message(BaseModel):
    answer_in_language: Optional[str] = Field("en") # default is English
    answer_in_format: str = Field("html", description="the format of answer")
    context: str = Field("chatbot", description="the context of question")
    question: str = Field("", description="the question for Q&A ")
    temperature_score: float = Field(DEFAULT_TEMPERATURE_SCORE, description="the temperature score of LLM ")
    visitor_id: str = Field("", description="the visitor id ")
    persona_id: str = Field("web_user", description="the persona id ")
    touchpoint_id: Optional[str] = Field(None, description="the touchpoint id ")
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    touchpoint_name: str = Field("Web visitor")
    touchpoint_description: str = Field("")
    touchpoint_type: str = Field("web", max_length=50)
    touchpoint_keywords: List[str] = Field(default_factory=list)
    result_limit: Optional[int] = Field(
        None, gt=0, strict=True, description="Nearby result count; overrides a count in the question."
    )


class GeolocationTouchpointRequest(BaseModel):
    visitor_id: str = Field(..., min_length=1, max_length=255)
    touchpoint_id: Optional[str] = Field(None, max_length=64)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    name: str = Field("Web visitor")
    description: str = Field("")
    type: str = Field("web", max_length=50)
    keywords: List[str] = Field(default_factory=list)

    
    
# Data models
class ChatMessage(BaseModel):
    profile_id: str = Field("", description="the ID of CDP profile")
    event_id: str = Field("", description="the ID of tracking event")
    content: str = Field("", description="the content of chat message")
    
# UTM model
class UTMData(BaseModel):
    utmsource: Optional[str]
    utmmedium: Optional[str]
    utmcampaign: Optional[str]
    utmterm: Optional[str]
    utmcontent: Optional[str]

# EventData model
class EventData(BaseModel):
    phone: Optional[str]
    first_name: Optional[str]
    living_district: Optional[str]
    living_city: Optional[str]
    marital_status: Optional[str]
    personal_interests: List[str]
    gift_code: Optional[str]

# Payload model
class Payload(BaseModel):
    datetime: datetime
    obsid: str
    mediahost: str
    tprefurl: Optional[str]
    tprefdomain: Optional[str]
    tpurl: HttpUrl
    tpname: str
    metric: str
    eventdata: EventData
    visid: str
    fgp: str
    ctxsk: str

class TrackedEvent(BaseModel):
    utmdata: Optional[UTMData]
    payload: Payload
  